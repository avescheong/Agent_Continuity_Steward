"""Caveman Context Validator.

Validation, reasoning, and auditability layer for Caveman Context Extraction.
Enforces:
1. Conversation Authority (AI statement = Recommendation; Human statement = Decision).
2. Speculative Filter (Filters out brainstorming, "what if", "maybe", comparisons).
3. Pronoun Resolution (Resolves "it", "this", "that" to preceding AI proposals).
4. Decision Evolution (Handles reversals, superseded choices, "changed my mind").
5. Semantic Deduplication (Subsumption merging for constraints and tasks).
6. Conflict Detection (Detects contradictions between constraints and decisions).
7. Evidence Traceability (Maps every record to fragment, turn, and quote).
8. Strict Question Handling (Questions are NOT Tasks).
9. Exact Identifier Preservation (paths, files, symbols, SHAs).
"""

import re
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass, field


@dataclass
class ConversationTurn:
    speaker: str  # "AI", "HUMAN", or "UNKNOWN"
    text: str
    fragment_idx: int = 1
    turn_idx: int = 1


@dataclass
class ConversationAct:
    act_type: str  # "PROPOSAL", "DISCUSSION", "AGREEMENT", "REJECTION", "REVERSAL", "DIRECT_DECISION"
    speaker: str   # "AI", "HUMAN", "UNKNOWN"
    subject: str   # Clean canonical subject
    full_proposition: str  # Complete grammatical proposition
    reasoning: str # Explanatory clause or why
    evidence_quote: str # Exact line from conversation
    fragment_idx: int
    turn_idx: int
    supersedes: str = "" # In case of REVERSAL, what is superseded
    confidence: str = "HIGH"


def sanitize_proposition(text: str, default_verb: str = "") -> str:
    """Removes Markdown syntax, list prefixes, and ensures a clean, complete proposition."""
    if not text:
        return ""
    s = text.strip()
    # Strip markdown headers (e.g. "### 2. Key Decisions")
    s = re.sub(r"^#+\s*", "", s)
    # Strip list markers, checkboxes, and bullets: "- [ ] ", "* [x] ", "1. ", "• "
    s = re.sub(r"^\s*[-*•]?\s*(?:\[\s*[ xX]?\s*\])?\s*", "", s)
    s = re.sub(r"^\s*\d+[\.\)]\s*", "", s)
    # Strip leading prefixes: "Decision:", "Proposal:", "Recommendation:", "Constraint:"
    s = re.sub(r"^(?:decision|proposal|recommendation|constraint|limitation|task|note):\s*", "", s, flags=re.IGNORECASE)
    # Strip markdown bold/italic tags: **text** or *text* or __text__ or _text_
    s = re.sub(r"\*\*([^*]+)\*\*", r"\1", s)
    s = re.sub(r"__([^_]+)__", r"\1", s)
    s = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"\1", s)
    # Strip backticks: `code` -> code
    s = re.sub(r"`([^`]+)`", r"\1", s)
    # Strip any dangling / unclosed markdown markers
    s = s.replace("**", "").replace("__", "").replace("`", "")
    # Strip leading/trailing quotation marks, colons, semicolons, dashes, asterisks
    s = s.strip("\"'`:;- *").rstrip(".:;, *")
    # Clean leading punctuation noise like "', "
    s = re.sub(r"^['\",\s]+", "", s).strip()
    # Clean leading conjunctions like "or ", "and "
    s = re.sub(r"^(?:or|and)\s+", "", s, flags=re.IGNORECASE).strip()
    # Clean trailing connective words like "instead", "for now", "first"
    s = re.sub(r"\s+(?:instead|for now|first|here)$", "", s, flags=re.IGNORECASE).strip()

    if default_verb and not any(s.lower().startswith(v) for v in ("use", "adopt", "implement", "configure", "deploy", "build", "create", "set up")):
        s = f"{default_verb} {s}"

    # Capitalize first character
    if s and s[0].islower():
        s = s[0].upper() + s[1:]
    return s


class CavemanContextValidator:
    """Reasoning, validation, and auditability gate for Caveman Context Extraction."""

    # Words that signal interrogative questions rather than action tasks
    QUESTION_STARTERS = (
        "what", "why", "how", "when", "where", "who", "which", "whose", "whom",
        "should we", "can we", "could we", "would we", "shall we",
        "is there", "are there", "is it", "are they", "do we", "does it",
        "have we", "has it"
    )

    # Words that signal speculative discussion rather than confirmed commitments
    SPECULATIVE_SIGNALS = (
        "maybe", "perhaps", "what if", "could consider", "might consider",
        "evaluating", "pros and cons", "whereas", "experiment", "brainstorming",
        "one option is", "hypothetically", "probably", "just thinking"
    )

    # Words that signal hard constraints and operational rules
    CONSTRAINT_SIGNALS = (
        "must", "cannot", "can't", "should not", "strictly", "offline", "modular",
        "never", "prohibit", "require", "limit", "maximum", "minimum", "under ",
        "no cloud", "no remote", "zero-configuration", "read-only", "isolated",
        "boundary", "frozen", "freeze", "preserve", "non-negotiable", "invariant",
        "forbidden", "do not break", "do not modify", "do not alter", "do not redesign",
        "governance"
    )

    # Words that signal ambiguous / provisional / deferred agreement
    AMBIGUOUS_CONFIRM_SIGNALS = (
        "but", "however", "maybe", "not sure", "sleep on it", "wait", "hold on",
        "not yet", "think about it", "defer", "tentative", "provisional", "later"
    )

    # Incomplete or invalid token labels
    INVALID_DANGLES = (
        "refactor:", "refactor", "constraint:", "limitation:", "todo:", "fixme:",
        "feat:", "fix:", "chore:", "docs:", "test:", "style:"
    )

    def parse_turns(self, raw_fragments: List[str]) -> List[ConversationTurn]:
        """Segments raw text lines into structured speaker turns with fragment and turn indices."""
        turns: List[ConversationTurn] = []
        ai_prefix = re.compile(
            r"^(?:#{1,4}\s*)?(?:\*\*)?(?:AI|Assistant|Claude|ChatGPT|Gemini|Argon|Model|Bot)(?:\s+said)?(?:\*\*)?:\s*",
            re.IGNORECASE,
        )
        human_prefix = re.compile(
            r"^(?:#{1,4}\s*)?(?:\*\*)?(?:Human|User|You|Developer|Me|Operator)(?:\s+said)?(?:\*\*)?:\s*",
            re.IGNORECASE,
        )

        turn_counter = 1
        for f_idx, frag in enumerate(raw_fragments, 1):
            current_speaker = "UNKNOWN"
            current_lines: List[str] = []

            for line in frag.splitlines():
                l_strip = line.strip()
                if not l_strip:
                    continue

                if human_prefix.match(l_strip):
                    if current_lines:
                        turns.append(ConversationTurn(
                            speaker=current_speaker,
                            text="\n".join(current_lines),
                            fragment_idx=f_idx,
                            turn_idx=turn_counter,
                        ))
                        turn_counter += 1
                        current_lines = []
                    current_speaker = "HUMAN"
                    rem = human_prefix.sub("", l_strip).strip()
                    if rem:
                        current_lines.append(rem)
                elif ai_prefix.match(l_strip):
                    if current_lines:
                        turns.append(ConversationTurn(
                            speaker=current_speaker,
                            text="\n".join(current_lines),
                            fragment_idx=f_idx,
                            turn_idx=turn_counter,
                        ))
                        turn_counter += 1
                        current_lines = []
                    current_speaker = "AI"
                    rem = ai_prefix.sub("", l_strip).strip()
                    if rem:
                        current_lines.append(rem)
                else:
                    current_lines.append(l_strip)

            if current_lines:
                turns.append(ConversationTurn(
                    speaker=current_speaker,
                    text="\n".join(current_lines),
                    fragment_idx=f_idx,
                    turn_idx=turn_counter,
                ))
                turn_counter += 1

        return turns

    def parse_conversation_acts(self, turns: List[ConversationTurn]) -> List[ConversationAct]:
        """Classifies turns into structured conversation acts prioritizing communicative intentions."""
        acts: List[ConversationAct] = []

        rec_regex = re.compile(
            r"(?:i recommend|i'?d recommend|my recommendation is|we recommend|we suggest|i suggest|a good option (?:is|would be)|consider (?:using|adopting)|recommend(?:s|ing)?|proposal:?)\s+([^.\n]+?)(?:\s+(?:because of|because|since|as|for|why:)\s+([^.\n]+))?[.]*$",
            re.IGNORECASE | re.MULTILINE
        )
        human_confirm_regex = re.compile(
            r"^(?:yes|proceed|agreed|sounds good|approved|confirm|confirmed|let'?s do (?:this|that)|go ahead|adopt|accept)(?:[,.\s].*|\s+with\s+(?:this|that)\s+approach)?$",
            re.IGNORECASE
        )
        human_direct_dec_regex = re.compile(
            r"(?:let'?s (?:use|go with|stick to|choose|adopt)|we decided to|we will use|decision:\s*|agreed to)\s+([^\n]+)",
            re.IGNORECASE
        )
        pronoun_dec_regex = re.compile(
            r"(?:let'?s (?:use|go with|choose|stick to|adopt)|adopt|take)\s+(?:it|this|that)\b(?:\s+(?:because of|because|since|as|why:)\s+(.+))?",
            re.IGNORECASE
        )
        reversal_regex = re.compile(
            r"\b(?:changed my mind|change of plans?|instead of|actually let'?s|supersedes?|replaces?|scrapped|cancelling|reversing)\b",
            re.IGNORECASE
        )
        explicit_reject_target = re.compile(
            r"\b(?:do not use|don'?t use|avoid|reject(?:ed)?|not using|scrapped|cancelling|scrapping|abandoning|dropping|ruled out|discarded|opted against)\s+([A-Za-z0-9_\-]+(?:\s+[A-Za-z0-9_\-]+){0,4}?)(?=\s+(?:because|since|as|due to|in favor of|for)\b|[.,;]|$)",
            re.IGNORECASE
        )

        for turn in turns:
            turn_no_code = re.sub(r"```[\s\S]*?```", "", turn.text)
            raw_lines = [l.strip() for l in turn_no_code.splitlines() if l.strip()]
            lines: List[str] = []
            for rl in raw_lines:
                # Guard against minified/base64 blobs in multi-hundred-message transcripts
                if max((len(tok) for tok in rl.split()), default=0) > 350:
                    continue
                lines.append(rl[:1500] if len(rl) > 1500 else rl)

            if turn.speaker == "AI":
                for line in lines:
                    # Filter out speculative brainstorming
                    if any(sig in line.lower() for sig in self.SPECULATIVE_SIGNALS):
                        acts.append(ConversationAct(
                            act_type="DISCUSSION",
                            speaker="AI",
                            subject="Speculative exploration",
                            full_proposition=line,
                            reasoning="AI exploration / brainstorming",
                            evidence_quote=line,
                            fragment_idx=turn.fragment_idx,
                            turn_idx=turn.turn_idx,
                            confidence="LOW",
                        ))
                        continue

                    m = rec_regex.search(line)
                    if m:
                        stmt = m.group(1).strip().rstrip(".")
                        why = m.group(2).strip().rstrip(".") if m.group(2) else "Proposed in AI discussion"
                        if stmt and len(stmt) > 3:
                            clean_subj = sanitize_proposition(stmt)
                            clean_prop = sanitize_proposition(stmt, default_verb="Adopt")
                            acts.append(ConversationAct(
                                act_type="PROPOSAL",
                                speaker="AI",
                                subject=clean_subj,
                                full_proposition=clean_prop,
                                reasoning=why,
                                evidence_quote=line,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="MEDIUM",
                            ))
                    else:
                        m_tech = re.search(r"(?:could use|can use|option is|try|recommend)\s+([A-Za-z0-9_\-]+(?:\s+[A-Za-z0-9_\-]+)?)", line, re.IGNORECASE)
                        if m_tech and not any(sig in line.lower() for sig in self.SPECULATIVE_SIGNALS):
                            tech = m_tech.group(1).strip()
                            if len(tech) > 2 and tech.lower() not in ("the", "this", "that", "it"):
                                clean_subj = sanitize_proposition(tech)
                                acts.append(ConversationAct(
                                    act_type="PROPOSAL",
                                    speaker="AI",
                                    subject=clean_subj,
                                    full_proposition=f"Use {clean_subj}",
                                    reasoning="Proposed in AI discussion",
                                    evidence_quote=line,
                                    fragment_idx=turn.fragment_idx,
                                    turn_idx=turn.turn_idx,
                                    confidence="MEDIUM",
                                ))

            elif turn.speaker == "HUMAN":
                for line in lines:
                    # Break compound multi-sentence lines into individual sentence clauses
                    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", line) if s.strip()] or [line]
                    for sent in sentences:
                        # Filter out speculative questions / brainstorming from human
                        if "?" in sent or any(sig in sent.lower() for sig in self.SPECULATIVE_SIGNALS):
                            acts.append(ConversationAct(
                                act_type="DISCUSSION",
                                speaker="HUMAN",
                                subject="Human inquiry",
                                full_proposition=sent,
                                reasoning="Exploratory discussion or question",
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="LOW",
                            ))
                            continue

                        # 1. Reversals: "Instead of X, let's use Y" or "Let's use Y instead of X"
                        why_m = re.search(r"\b(?:because of|because|since|as|why:)\b\s*(.+)$", sent, re.IGNORECASE)
                        clause = sent[:why_m.start()].strip() if why_m else sent
                        extracted_why = why_m.group(1).strip().rstrip(".") if why_m else ""
                        clause = clause.rstrip(".,;: ")

                        m_instead_1 = re.search(
                            r"instead of\s+([A-Za-z0-9_\-\s`\"']+?)[,.]?\s+(?:let'?s (?:use|go with|choose|adopt)|we will use|adopt)\s+([A-Za-z0-9_\-\s`\"']+?)$",
                            clause,
                            re.IGNORECASE
                        )
                        m_instead_2 = re.search(
                            r"(?:let'?s (?:use|go with|choose|adopt)|we will use|adopt)\s+([A-Za-z0-9_\-\s`\"']+?)\s+instead of\s+([A-Za-z0-9_\-\s`\"']+?)$",
                            clause,
                            re.IGNORECASE
                        )
                        if m_instead_1 or m_instead_2:
                            if m_instead_1:
                                old_item = m_instead_1.group(1).strip()
                                new_item = m_instead_1.group(2).strip()
                            else:
                                new_item = m_instead_2.group(1).strip()
                                old_item = m_instead_2.group(2).strip()

                            why_str = extracted_why or f"Adopted instead of {old_item}"

                            clean_old = sanitize_proposition(old_item)
                            clean_new = sanitize_proposition(new_item, default_verb="Use")
                            acts.append(ConversationAct(
                                act_type="REVERSAL",
                                speaker="HUMAN",
                                subject=clean_new,
                                full_proposition=clean_new,
                                supersedes=clean_old,
                                reasoning=why_str,
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="HIGH",
                            ))
                            continue

                        # 2. Partial Agreement: "I agree with using X, but do not use Y"
                        m_agree = re.search(
                            r"(?:i agree with (?:using|adopting|the)?|agreed on|agree to)\s+([A-Za-z0-9_\-]+(?:\s+[A-Za-z0-9_\-]+)?)",
                            sent,
                            re.IGNORECASE
                        )
                        m_rej_in_agree = explicit_reject_target.search(sent)
                        if m_agree:
                            agreed_item = sanitize_proposition(m_agree.group(1).strip(), default_verb="Use")
                            why_m = re.search(r"\b(?:because of|because|since|as|why:)\b\s*(.+)$", sent, re.IGNORECASE)
                            agree_why = why_m.group(1).strip().rstrip(".") if why_m else "Agreed by Human in conversation"
                            acts.append(ConversationAct(
                                act_type="AGREEMENT",
                                speaker="HUMAN",
                                subject=agreed_item,
                                full_proposition=agreed_item,
                                reasoning=agree_why,
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="HIGH",
                            ))
                            if m_rej_in_agree:
                                rej_item = sanitize_proposition(m_rej_in_agree.group(1).strip())
                                acts.append(ConversationAct(
                                    act_type="REJECTION",
                                    speaker="HUMAN",
                                    subject=rej_item,
                                    full_proposition=f"Do not use {rej_item}",
                                    reasoning=agree_why,
                                    evidence_quote=sent,
                                    fragment_idx=turn.fragment_idx,
                                    turn_idx=turn.turn_idx,
                                    confidence="HIGH",
                                ))
                            continue

                        # 3. Explicit Rejection: "Do not use X because Y"
                        m_rej_target = explicit_reject_target.search(sent)
                        if m_rej_target:
                            rej_item = sanitize_proposition(m_rej_target.group(1).strip())
                            why_m = re.search(r"\b(?:because of|because|due to|since|as|why:)\b\s*(.+)$", sent, re.IGNORECASE)
                            rej_why = why_m.group(1).strip().rstrip(".") if why_m else "Not aligned with project goals or constraints"
                            acts.append(ConversationAct(
                                act_type="REJECTION",
                                speaker="HUMAN",
                                subject=rej_item,
                                full_proposition=f"Do not use {rej_item}",
                                reasoning=rej_why,
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="HIGH",
                            ))
                            continue

                        # 4. Human Agreement / Confirmation
                        if any(sig in sent.lower() for sig in self.AMBIGUOUS_CONFIRM_SIGNALS):
                            # Provisional hesitation is classified as DISCUSSION, never agreement!
                            acts.append(ConversationAct(
                                act_type="DISCUSSION",
                                speaker="HUMAN",
                                subject="Provisional hesitation",
                                full_proposition=sent,
                                reasoning="Ambiguous confirmation / deferred commitment",
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="LOW",
                            ))
                            continue

                        m_pronoun = pronoun_dec_regex.search(sent)
                        if m_pronoun:
                            why = m_pronoun.group(1).strip().rstrip(".") if m_pronoun.group(1) else ""
                            acts.append(ConversationAct(
                                act_type="AGREEMENT",
                                speaker="HUMAN",
                                subject="PREV_PROPOSAL",
                                full_proposition="Adopt previous proposal",
                                reasoning=why,
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="HIGH",
                            ))
                            continue

                        if human_confirm_regex.search(sent):
                            acts.append(ConversationAct(
                                act_type="AGREEMENT",
                                speaker="HUMAN",
                                subject="PREV_PROPOSAL",
                                full_proposition="Confirmed proposal",
                                reasoning="Recommended by AI and approved by Human",
                                evidence_quote=sent,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="HIGH",
                            ))
                            continue

                        # 5. Direct Human Decision: "Let's use X because Y"
                        m_direct = human_direct_dec_regex.search(sent)
                        if m_direct:
                            full_choice = m_direct.group(1).strip().rstrip(".")
                            why_m = re.search(r"\b(?:because of|because|since|as|why:)\b\s*(.+)$", full_choice, re.IGNORECASE)
                            if why_m:
                                choice_title = full_choice[:why_m.start()].strip().rstrip("(")
                                choice_why = why_m.group(1).strip().rstrip(")")
                            else:
                                choice_title = full_choice
                                choice_why = "Confirmed by Human in conversation"

                            clean_prop = sanitize_proposition(choice_title, default_verb="Use")
                            clean_subj = sanitize_proposition(choice_title)
                            if clean_subj.lower() not in ("it", "this", "that") and not any(sig in clean_subj.lower() for sig in self.SPECULATIVE_SIGNALS):
                                acts.append(ConversationAct(
                                    act_type="DIRECT_DECISION",
                                    speaker="HUMAN",
                                    subject=clean_subj,
                                    full_proposition=clean_prop,
                                    reasoning=choice_why,
                                    evidence_quote=sent,
                                    fragment_idx=turn.fragment_idx,
                                    turn_idx=turn.turn_idx,
                                    confidence="HIGH",
                                ))
                                continue

            elif turn.speaker == "UNKNOWN":
                for line in lines:
                    m_direct = human_direct_dec_regex.search(line)
                    if m_direct:
                        full_choice = m_direct.group(1).strip().rstrip(".")
                        why_m = re.search(r"\b(?:because of|because|since|as|why:)\b\s*(.+)$", full_choice, re.IGNORECASE)
                        if why_m:
                            choice_title = full_choice[:why_m.start()].strip().rstrip("(")
                            choice_why = why_m.group(1).strip().rstrip(")")
                        else:
                            choice_title = full_choice
                            choice_why = "Confirmed in conversation"
                        clean_prop = sanitize_proposition(choice_title, default_verb="Use")
                        clean_subj = sanitize_proposition(choice_title)
                        if clean_subj.lower() not in ("it", "this", "that") and not any(sig in clean_subj.lower() for sig in self.SPECULATIVE_SIGNALS):
                            acts.append(ConversationAct(
                                act_type="DIRECT_DECISION",
                                speaker="UNKNOWN",
                                subject=clean_subj,
                                full_proposition=clean_prop,
                                reasoning=choice_why,
                                evidence_quote=line,
                                fragment_idx=turn.fragment_idx,
                                turn_idx=turn.turn_idx,
                                confidence="MEDIUM",
                            ))

        return acts

    def validate_authority_and_decisions(
        self,
        turns: List[ConversationTurn],
        raw_decisions: List[Any],
        raw_rejected: List[Dict[str, str]],
        raw_fragments: List[str],
    ) -> Tuple[List[Any], List[Dict[str, str]], List[Dict[str, str]], List[str], Dict[str, Any]]:
        """
        Enforces:
        - Authority Gate: AI recommendation != Human decision.
        - Speculative Filter: Rejects brainstorming / 'what if' / comparisons.
        - Pronoun Resolution: Resolves 'it' / 'this' / 'that' to preceding AI proposal.
        - Decision Evolution: Detects reversals and superseded choices.
        - Evidence Traceability: Populates provenance matrix for auditability.
        """
        from src.scs_core.modules.caveman_engine import CausalDecision

        confirmed_decisions: List[CausalDecision] = []
        recommendations: List[Dict[str, str]] = []
        rejected_options: List[Dict[str, str]] = list(raw_rejected)
        unclassified_context: List[str] = []
        traceability_matrix: Dict[str, Any] = {}

        # 1. Parse conversation acts prioritizing communicative acts over raw regexes
        acts = self.parse_conversation_acts(turns)

        # Track proposals: List of ConversationAct
        proposals: List[ConversationAct] = []

        for act in acts:
            if act.act_type == "PROPOSAL":
                proposals.append(act)

            elif act.act_type == "AGREEMENT":
                if act.subject == "PREV_PROPOSAL" and proposals:
                    last_prop = proposals[-1]
                    title = last_prop.full_proposition
                    why = act.reasoning or last_prop.reasoning
                    dec_code = f"DEC-{len(confirmed_decisions)+1:03d}"
                    d = CausalDecision(
                        code=dec_code,
                        title=title,
                        problem=f"Proposal evaluated: {last_prop.subject}",
                        recommendation=last_prop.subject,
                        human_decision=f"Confirmed: {title}",
                        reasoning=why,
                        resulting_action="Adopted in project implementation",
                        source_fragment_idx=act.fragment_idx,
                        source_turn_idx=act.turn_idx,
                        evidence_quote=act.evidence_quote,
                        confidence="HIGH",
                    )
                    confirmed_decisions.append(d)
                    traceability_matrix[dec_code] = {
                        "fragment_idx": act.fragment_idx,
                        "turn_idx": act.turn_idx,
                        "speaker": "HUMAN",
                        "quote": act.evidence_quote,
                        "confidence": "HIGH",
                    }
                elif act.subject != "PREV_PROPOSAL":
                    title = act.full_proposition
                    dec_code = f"DEC-{len(confirmed_decisions)+1:03d}"
                    d = CausalDecision(
                        code=dec_code,
                        title=title,
                        human_decision=f"Confirmed: {title}",
                        reasoning=act.reasoning,
                        resulting_action="Adopted in project implementation",
                        source_fragment_idx=act.fragment_idx,
                        source_turn_idx=act.turn_idx,
                        evidence_quote=act.evidence_quote,
                        confidence="HIGH",
                    )
                    if not any(cd.title.lower() == title.lower() for cd in confirmed_decisions):
                        confirmed_decisions.append(d)
                        traceability_matrix[dec_code] = {
                            "fragment_idx": act.fragment_idx,
                            "turn_idx": act.turn_idx,
                            "speaker": "HUMAN",
                            "quote": act.evidence_quote,
                            "confidence": "HIGH",
                        }

            elif act.act_type == "DIRECT_DECISION":
                title = act.full_proposition
                if not any(cd.title.lower() == title.lower() for cd in confirmed_decisions):
                    dec_code = f"DEC-{len(confirmed_decisions)+1:03d}"
                    d = CausalDecision(
                        code=dec_code,
                        title=title,
                        human_decision=f"Confirmed: {title}",
                        reasoning=act.reasoning,
                        resulting_action="Adopted in project implementation",
                        source_fragment_idx=act.fragment_idx,
                        source_turn_idx=act.turn_idx,
                        evidence_quote=act.evidence_quote,
                        confidence=act.confidence,
                    )
                    confirmed_decisions.append(d)
                    traceability_matrix[dec_code] = {
                        "fragment_idx": act.fragment_idx,
                        "turn_idx": act.turn_idx,
                        "speaker": act.speaker,
                        "quote": act.evidence_quote,
                        "confidence": act.confidence,
                    }

            elif act.act_type == "REVERSAL":
                # Superseded item moves to rejected options
                rej_code = f"REJ-{len(rejected_options)+1:03d}"
                rejected_options.append({
                    "code": rej_code,
                    "statement": act.supersedes,
                    "why": f"Discarded in favor of {act.subject}",
                    "quote": act.evidence_quote,
                })
                traceability_matrix[rej_code] = {
                    "fragment_idx": act.fragment_idx,
                    "turn_idx": act.turn_idx,
                    "speaker": act.speaker,
                    "quote": act.evidence_quote,
                    "confidence": "HIGH",
                }
                # Remove earlier decision matching superseded item
                clean_superseded_core = re.sub(r"^(?:use|adopt|choose|select)\s+", "", act.supersedes.lower()).strip()
                if clean_superseded_core:
                    confirmed_decisions = [
                        d for d in confirmed_decisions
                        if clean_superseded_core not in re.sub(r"^(?:use|adopt|choose|select)\s+", "", d.title.lower()).strip()
                        and re.sub(r"^(?:use|adopt|choose|select)\s+", "", d.title.lower()).strip() not in clean_superseded_core
                        and act.supersedes.lower() not in d.title.lower()
                    ]

                # Add new item as confirmed decision
                dec_code = f"DEC-{len(confirmed_decisions)+1:03d}"
                d = CausalDecision(
                    code=dec_code,
                    title=act.full_proposition,
                    problem=f"Replaced {act.supersedes} with {act.subject}",
                    recommendation=act.subject,
                    human_decision=f"Confirmed: {act.full_proposition}",
                    reasoning=act.reasoning,
                    resulting_action="Adopted in project implementation",
                    source_fragment_idx=act.fragment_idx,
                    source_turn_idx=act.turn_idx,
                    evidence_quote=act.evidence_quote,
                    confidence="HIGH",
                )
                confirmed_decisions.append(d)
                traceability_matrix[dec_code] = {
                    "fragment_idx": act.fragment_idx,
                    "turn_idx": act.turn_idx,
                    "speaker": act.speaker,
                    "quote": act.evidence_quote,
                    "confidence": "HIGH",
                }

            elif act.act_type == "REJECTION":
                if not any(r["statement"].lower() == act.subject.lower() for r in rejected_options):
                    rej_code = f"REJ-{len(rejected_options)+1:03d}"
                    rejected_options.append({
                        "code": rej_code,
                        "statement": act.subject,
                        "why": act.reasoning,
                        "quote": act.evidence_quote,
                    })
                    traceability_matrix[rej_code] = {
                        "fragment_idx": act.fragment_idx,
                        "turn_idx": act.turn_idx,
                        "speaker": act.speaker,
                        "quote": act.evidence_quote,
                        "confidence": "HIGH",
                    }
                    # Also remove from decisions if previously recorded
                    clean_rej_core = re.sub(r"^(?:use|adopt|choose|select)\s+", "", act.subject.lower()).strip()
                    if clean_rej_core:
                        confirmed_decisions = [
                            d for d in confirmed_decisions
                            if clean_rej_core not in re.sub(r"^(?:use|adopt|choose|select)\s+", "", d.title.lower()).strip()
                            and re.sub(r"^(?:use|adopt|choose|select)\s+", "", d.title.lower()).strip() not in clean_rej_core
                            and act.subject.lower() not in d.title.lower()
                        ]

        # Unconfirmed AI proposals remain as recommendations
        for p in proposals:
            already_confirmed = any(p.subject.lower() in d.title.lower() or d.title.lower() in p.subject.lower() for d in confirmed_decisions)
            already_rejected = any(p.subject.lower() in r["statement"].lower() for r in rejected_options)
            if not already_confirmed and not already_rejected:
                rec_code = f"REC-{len(recommendations)+1:03d}"
                recommendations.append({
                    "code": rec_code,
                    "statement": f"{p.subject} proposed as an option",
                    "status": "Awaiting human decision",
                    "proposed_by": p.speaker,
                    "reasoning": p.reasoning or "Proposed during discussion",
                    "quote": p.evidence_quote,
                })
                traceability_matrix[rec_code] = {
                    "fragment_idx": p.fragment_idx,
                    "turn_idx": p.turn_idx,
                    "speaker": p.speaker,
                    "quote": p.evidence_quote,
                }

        # Process raw decisions extracted from regexes if not already captured
        has_any_human = any(t.speaker == "HUMAN" for t in turns)
        for d in raw_decisions:
            d_clean = sanitize_proposition(d.title, default_verb="Use")
            if len(d_clean) < 4 or d_clean.lower() in self.INVALID_DANGLES:
                unclassified_context.append(f"Incomplete decision: {d.title}")
                continue
            if any(sig in d.title.lower() for sig in self.SPECULATIVE_SIGNALS):
                unclassified_context.append(f"Speculative comparison: {d.title}")
                continue

            # Check if this raw decision was superseded / rejected
            already_rejected = any(r["statement"].lower() in d_clean.lower() or d_clean.lower() in r["statement"].lower() for r in rejected_options)
            if already_rejected:
                continue

            if has_any_human and not any(d_clean.lower() in cd.title.lower() or cd.title.lower() in d_clean.lower() for cd in confirmed_decisions):
                if not any(d_clean.lower() in r["statement"].lower() for r in recommendations):
                    rec_code = f"REC-{len(recommendations)+1:03d}"
                    recommendations.append({
                        "code": rec_code,
                        "statement": f"{d_clean} proposed as an option",
                        "status": "Awaiting human decision",
                        "proposed_by": "AI",
                        "reasoning": d.reasoning or "Proposed during discussion",
                        "quote": d.evidence_quote or d.title,
                    })
                continue

            if not has_any_human and not any(cd.title.lower() == d_clean.lower() for cd in confirmed_decisions):
                dec_code = f"DEC-{len(confirmed_decisions)+1:03d}"
                d.code = dec_code
                d.title = d_clean
                confirmed_decisions.append(d)
                traceability_matrix[dec_code] = {
                    "fragment_idx": getattr(d, "source_fragment_idx", 1),
                    "turn_idx": 1,
                    "speaker": "CONSENSUS",
                    "quote": d.evidence_quote or d.title,
                }

        return confirmed_decisions, recommendations, rejected_options, unclassified_context, traceability_matrix

    def validate_constraints(self, raw_constraints: List[str], raw_text: str) -> Tuple[List[str], List[str]]:
        """
        Constraint Validation Gate & Canonical Semantic Consolidation:
        - Removes Markdown syntax and bullet prefixes.
        - Requires limitation rule, scope, and impact.
        - Rejects incomplete dangles (e.g. 'Constraint: refactor:').
        - Consolidates semantically identical constraints into richer canonical constraints.
        """
        candidate_constraints: List[str] = []
        unclassified: List[str] = []

        # Check raw text for dangling constraint lines like "Constraint:\nrefactor:" or "Constraint: refactor:"
        dangle_pat = re.compile(r"^(?:constraint|limitation):\s*(refactor:?|TODO:?|fix:?|[a-z0-9_\-]+:)\s*$", re.IGNORECASE | re.MULTILINE)
        for m in dangle_pat.finditer(raw_text):
            val = m.group(1).strip()
            unclassified.append(f"Constraint: {val}")

        for c in raw_constraints:
            c_clean = sanitize_proposition(c)
            c_lower = c_clean.lower()

            # 1. Reject if ends in colon or matches invalid dangles
            if c_clean.endswith(":") or c_lower in self.INVALID_DANGLES:
                unclassified.append(f"Constraint: {c_clean}")
                continue

            # 2. Reject if ends in question mark or is interrogative
            if c_clean.endswith("?") or any(c_lower.startswith(q) for q in self.QUESTION_STARTERS):
                unclassified.append(f"Constraint (question): {c_clean}")
                continue

            # 3. Reject if under 3 words or ends with dangling incomplete object
            words = c_clean.split()
            if len(words) < 3:
                unclassified.append(f"Constraint (fragment): {c_clean}")
                continue
            if words[-1].lower() in ("raw", "a", "an", "the", "new", "handle", "run", "do"):
                unclassified.append(f"Constraint (dangle): {c_clean}")
                continue

            # 4. Must contain limitation semantics
            has_signal = any(sig in c_lower for sig in self.CONSTRAINT_SIGNALS)
            if not has_signal:
                unclassified.append(f"Constraint: {c_clean}")
                continue

            candidate_constraints.append(c_clean)

        # Semantic Clusters for Canonical Consolidation
        SEMANTIC_CLUSTERS = [
            # Offline / Network boundary
            {"offline", "internet", "network", "remote", "cloud", "air-gapped", "no remote", "no cloud"},
            # Storage / File size boundary
            {"50mb", "file size", "storage limit", "remain under", "disk space", "maximum size", "size under"},
            # Modular / Single binary architecture
            {"modular", "single-binary", "standalone", "loose coupling", "zero configuration", "zero-config", "no external daemon"},
            # Security / Credentials
            {"secret", "password", "token", "credential", "auth", "unencrypted", "encryption"},
            # Performance limits
            {"latency", "throughput", "ops/sec", "ram footprint", "memory limit", "heap"},
        ]

        def constraint_richness(text: str) -> int:
            score = len(text)
            for signal in ("must", "strictly", "100%", "without", "never", "cannot", "remain under", "completely"):
                if signal in text.lower():
                    score += 25
            return score

        consolidated: List[str] = []
        for c in candidate_constraints:
            c_low = c.lower()
            matched_existing_idx = None

            for idx, existing in enumerate(consolidated):
                ex_low = existing.lower()
                # Check direct substring subsumption
                if c_low in ex_low or ex_low in c_low:
                    matched_existing_idx = idx
                    break

                # Check cluster membership
                for cluster in SEMANTIC_CLUSTERS:
                    c_matches = sum(1 for kw in cluster if kw in c_low)
                    ex_matches = sum(1 for kw in cluster if kw in ex_low)
                    if c_matches >= 2 and ex_matches >= 2:
                        matched_existing_idx = idx
                        break
                    elif c_matches >= 1 and ex_matches >= 1:
                        if ("offline" in c_low and "offline" in ex_low) or ("50mb" in c_low and "50mb" in ex_low):
                            matched_existing_idx = idx
                            break
                if matched_existing_idx is not None:
                    break

            if matched_existing_idx is not None:
                # Replace with the richer canonical constraint
                existing = consolidated[matched_existing_idx]
                if constraint_richness(c) > constraint_richness(existing):
                    consolidated[matched_existing_idx] = c
            else:
                consolidated.append(c)

        return consolidated, unclassified

    def validate_tasks_and_questions(
        self,
        pending_tasks: List[Dict[str, str]],
        completed_tasks: List[Dict[str, str]],
        open_questions: List[str],
        raw_text: str,
    ) -> Tuple[List[Dict[str, str]], List[Dict[str, str]], List[str]]:
        """
        Enforces:
        - Questions are NOT tasks!
        - Interrogative sentences and review questions are classified as OPEN_QUESTION.
        - Multi-question reviews (e.g. 'What is good? What is wrong? What are the gaps?')
          synthesize into clear Open Review Questions.
        """
        validated_pending: List[Dict[str, str]] = []
        validated_completed: List[Dict[str, str]] = completed_tasks
        validated_questions: List[str] = list(open_questions)

        # 1. Check for review questions in raw text
        review_regex = re.compile(r"what is good\?.*what is wrong\?.*what are the gaps\?", re.IGNORECASE | re.DOTALL)
        gaps_regex = re.compile(r"what are the gaps\?", re.IGNORECASE)

        if review_regex.search(raw_text):
            review_q = "Open Review Question: Evaluate current strengths, weaknesses, and gaps."
            validated_questions = [q for q in validated_questions if not ("what is good" in q.lower() and "what is wrong" in q.lower())]
            if not any("strengths, weaknesses, and gaps" in q for q in validated_questions):
                validated_questions.insert(0, review_q)
        elif gaps_regex.search(raw_text):
            if not any("what are the gaps" in q.lower() for q in validated_questions):
                validated_questions.append("What are the gaps?")

        # 2. Intercept tasks that are actually questions
        for t in pending_tasks:
            title = t.get("title", "").strip()
            clean_title = re.sub(r"^\s*[-*•]?\s*(?:\[\s*[ xX]?\s*\]\s*)?", "", title).strip()
            title_lower = clean_title.lower()

            is_question = (
                clean_title.endswith("?") or
                title_lower.startswith(self.QUESTION_STARTERS)
            )

            if is_question:
                should_m = re.match(r"^should we\s+(.+?)\??$", clean_title, re.IGNORECASE)
                if should_m:
                    sub_target = should_m.group(1).strip()
                    if sub_target.lower().startswith("add "):
                        sub_target = sub_target[4:].strip()
                    q_formatted = f"Evaluate whether {sub_target} is required."
                else:
                    q_formatted = clean_title

                if not any(q.lower() == q_formatted.lower() for q in validated_questions):
                    validated_questions.append(q_formatted)
            else:
                validated_pending.append(t)

        # 3. Clean all questions of list/checkbox prefixes, URL fragments, and polite sign-offs
        polite_signoff_pat = re.compile(
            r"^(?:how would you like to proceed|what would you like (?:me )?to do(?: next)?|"
            r"shall we proceed(?:\s+with\s+this)?|would you like me to (?:proceed|implement|continue|start)|"
            r"ready to (?:proceed|start)|does (?:this|that) (?:make sense|sound good|work for you)|"
            r"any (?:questions|thoughts|feedback)|let me know what you think)\??$",
            re.IGNORECASE,
        )
        url_noise_pat = re.compile(
            r"(?:https?://|com/(?:file|document|spreadsheets|presentation)/d/|/(?:edit|view)\?|(?:\?|&)usp=)",
            re.IGNORECASE,
        )
        cleaned_final_questions: List[str] = []
        for q in validated_questions:
            q_clean = re.sub(r"^\s*[-*•]?\s*(?:\[\s*[ xX]?\s*\]\s*)?", "", q).strip()
            if not q_clean:
                continue
            if url_noise_pat.search(q_clean) or " " not in q_clean:
                continue
            if polite_signoff_pat.match(q_clean):
                continue
            should_m = re.match(r"^should we\s+(.+?)\??$", q_clean, re.IGNORECASE)
            if should_m:
                sub_target = should_m.group(1).strip()
                if sub_target.lower().startswith("add "):
                    sub_target = sub_target[4:].strip()
                q_clean = f"Evaluate whether {sub_target} is required."
            if q_clean and not any(cq.lower() == q_clean.lower() for cq in cleaned_final_questions):
                cleaned_final_questions.append(q_clean)

        return validated_pending, validated_completed, cleaned_final_questions

    def validate_artifacts(self, artifacts: List[Dict[str, str]], raw_text: str) -> List[Dict[str, str]]:
        """
        Ensures exact identifier preservation:
        - Exact file paths, filenames, and extensions are never simplified or altered.
        - e.g. 'src/scs_core/modules/caveman_engine.py' is preserved verbatim.
        """
        validated: List[Dict[str, str]] = []
        path_pattern = re.compile(
            r"(?:[\s`\"'\(\[]|^)([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|html|css|json|md|sql|sh|bat|yaml|yml))(?=[`\"'\)\],;:!?\.\s]|$)",
            re.IGNORECASE
        )

        for m in path_pattern.finditer(raw_text):
            raw_path = m.group(1).strip()
            norm = raw_path.replace("\\", "/")
            if not any(a.get("path") == norm for a in validated):
                validated.append({
                    "path": norm,
                    "status": "Referenced in AI Discussion",
                })

        for a in artifacts:
            if not any(v.get("path") == a.get("path") for v in validated):
                validated.append(a)

        return validated

    def detect_conflicts(
        self,
        decisions: List[Any],
        constraints: List[str],
        rejected_options: List[Dict[str, str]],
        tasks: Optional[List[Dict[str, str]]] = None,
    ) -> List[Dict[str, str]]:
        """
        Contradiction & Conflict Detection Gate:
        - Detects contradictions between constraints and decisions (e.g. offline constraint vs cloud database decision).
        - Detects contradictions between constraints and tasks (e.g. offline constraint vs cloud deployment task).
        - Detects active decisions conflicting with rejected options.
        - Returns list of conflict descriptors.
        """
        conflicts: List[Dict[str, str]] = []

        offline_signals = ("offline", "no cloud", "no remote", "local only")
        cloud_signals = ("cloud", "firebase", "aws", "azure", "gcp", "remote server", "remote database", "lambda", "s3 bucket")

        # 1. Constraint vs Decision contradiction (Offline vs Cloud)
        offline_constraints = [c for c in constraints if any(s in c.lower() for s in offline_signals)]
        cloud_decisions = [d for d in decisions if any(s in getattr(d, "title", "").lower() for s in cloud_signals)]

        if offline_constraints and cloud_decisions:
            for c in offline_constraints:
                for d in cloud_decisions:
                    conflicts.append({
                        "type": "CONSTRAINT_DECISION_CONTRADICTION",
                        "statement_a": f"Constraint: {c}",
                        "statement_b": f"Decision: {d.title}",
                        "severity": "WARNING",
                        "impact": "Project constraint mandates offline execution, but decision introduces cloud dependency.",
                    })

        # 2. Constraint vs Task contradiction (Offline vs Cloud Task)
        if tasks and offline_constraints:
            cloud_tasks = [t for t in tasks if any(s in t.get("title", "").lower() for s in cloud_signals)]
            for c in offline_constraints:
                for t in cloud_tasks:
                    conflicts.append({
                        "type": "CONSTRAINT_TASK_CONTRADICTION",
                        "statement_a": f"Constraint: {c}",
                        "statement_b": f"Task: {t['title']}",
                        "severity": "WARNING",
                        "impact": "Project constraint mandates offline execution, but task introduces cloud infrastructure.",
                    })

        # 3. Decision vs Rejected Option contradiction (Attempting to use a rejected option)
        for d in decisions:
            d_title = getattr(d, "title", "").lower()
            for r in rejected_options:
                r_stmt = r.get("statement", "").lower()
                if (r_stmt in d_title or d_title in r_stmt) and len(r_stmt) > 3:
                    conflicts.append({
                        "type": "DECISION_REJECTED_CONTRADICTION",
                        "statement_a": f"Decision: {d.title}",
                        "statement_b": f"Rejected Option: {r['statement']}",
                        "severity": "WARNING",
                        "impact": f"Active decision '{d.title}' conflicts with recorded rejected option '{r['statement']}'.",
                    })

        return conflicts
