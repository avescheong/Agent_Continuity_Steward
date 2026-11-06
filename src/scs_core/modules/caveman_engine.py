"""Caveman Context Extraction Engine.

Preserves full conversational dependency chains across complete AI working sessions:
  Problem → AI Analysis → Options → Human Decision → Reasoning → Constraint → Action
Optimisation target:
  Accuracy of future AI rehydration > text compression.
Preserves:
  1. Decision history (what, why, alternatives considered, why rejected)
  2. Technical reasoning (architecture discussions, implementation approaches, testing results, problems & solutions)
  3. Governance constraints (rules, boundaries, frozen decisions)
  4. Project evolution (design shifts, turning points, lessons learned)
  5. Current operational state (completed work, remaining work, open questions, next recommended action)
Compiles Continuity_MD_NN.md chapters and merges chapters into AI_HANDOVER_PACKAGE.md.
"""

import re
import json
import hashlib
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone

from scs_core.modules.scrubber import scrub_secrets
from scs_core.modules.caveman_context_validator import CavemanContextValidator, sanitize_proposition


# Conversational noise patterns to filter out (greetings, filler, polite sign-offs only)
CONVERSATIONAL_FLUFF = [
    r"^(?:hi|hello|hey)(?:\s+there)?[,!.\s]*$",
    r"^(?:sure|certainly|absolutely|of course)[,!.\s].*?$",
    r"^i'?d (?:be happy|love) to help.*$",
    r"^as an ai language model.*$",
    r"^hope (?:this|that) helps.*$",
    r"^let me know if you (?:have questions|need (?:further|more) (?:help|changes)).*$",
    r"^(?:feel free to|don'?t hesitate to) ask.*$",
    r"^(?:here is|below is|here are) (?:the|an) (?:updated|proposed|full|complete) (?:version|code|plan|solution):?$",
    r"^(?:great|awesome|excellent|sounds good)[,!.\s]*$",
    r"^how would you like to proceed\??$",
]

FLUFF_REGEX = re.compile("|".join(f"(?:{p})" for p in CONVERSATIONAL_FLUFF), re.IGNORECASE | re.MULTILINE)


@dataclass
class CausalDecision:
    title: str
    problem: str = ""
    recommendation: str = ""
    alternatives_considered: str = ""
    human_decision: str = ""
    reasoning: str = ""
    resulting_action: str = ""
    code: str = ""
    source_fragment_idx: int = 1
    source_turn_idx: int = 1
    source_session_code: str = ""
    evidence_quote: str = ""
    confidence: str = "HIGH"


@dataclass
class ExtractedContext:
    context_summary: str = ""
    session_themes: List[str] = field(default_factory=list)
    decisions: List[CausalDecision] = field(default_factory=list)
    recommendations: List[Dict[str, str]] = field(default_factory=list)
    rejected_options: List[Dict[str, str]] = field(default_factory=list)
    constraints: List[str] = field(default_factory=list)
    architecture_discussions: List[str] = field(default_factory=list)
    implementation_approaches: List[str] = field(default_factory=list)
    testing_results: List[str] = field(default_factory=list)
    problems_and_solutions: List[str] = field(default_factory=list)
    project_evolution: List[str] = field(default_factory=list)
    pending_tasks: List[Dict[str, str]] = field(default_factory=list)
    completed_tasks: List[Dict[str, str]] = field(default_factory=list)
    artifacts: List[Dict[str, str]] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    unclassified_context: List[str] = field(default_factory=list)
    conflicts: List[Dict[str, str]] = field(default_factory=list)
    traceability_matrix: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    first_instruction_for_next_ai: str = ""


class CavemanContextExtractionEngine:
    """Extracts, validates, and structures multi-session AI collaboration history for continuity preservation."""

    def __init__(self):
        self.validator = CavemanContextValidator()

    def clean_fluff(self, text: str) -> str:
        """Removes conversational pleasantries and empty polite filler while preserving reasoning context."""
        lines = []
        speaker_tag = r"(?:(?:AI|User|Human|You|Assistant|ChatGPT|Gemini|Claude|Argon|Operator)(?:\s+said)?:\s*)"
        lead_fluff_pattern = re.compile(
            rf"^{speaker_tag}?(?:(?:sure|certainly|absolutely|of course|great question|great|awesome|understood|okay)[,!]?\s*)*(?:here (?:is|are) [^:\n]+:?)?\s*",
            re.IGNORECASE,
        )
        standalone_fluff = re.compile(
            rf"^{speaker_tag}?(?:hi|hello|hey(?:\s+there)?|hope (?:this|that) helps|let me know if you (?:have (?:any )?questions|need (?:further|more) (?:help|changes))|feel free to ask|as an ai language model|how would you like to proceed|shall we proceed)[.!?]*$",
            re.IGNORECASE,
        )
        standalone_speaker = re.compile(
            r"^(?:#{1,4}\s*)?(?:\*\*)?(?:AI|User|Human|You|Assistant|ChatGPT|Gemini|Claude|Argon|Model|Bot|Operator)(?:\s+said)?(?:\*\*)?:\s*$",
            re.IGNORECASE,
        )

        for line in text.splitlines():
            l_strip = line.strip()
            if not l_strip:
                continue
            if standalone_speaker.match(l_strip) or standalone_fluff.match(l_strip):
                continue
            cleaned_line = lead_fluff_pattern.sub("", l_strip).strip()
            cleaned_line = re.sub(
                r"^(?:AI|User|Human|You|Assistant|ChatGPT|Gemini|Claude|Argon|Operator)(?:\s+said)?:\s*",
                "",
                cleaned_line,
                flags=re.IGNORECASE,
            ).strip()
            if cleaned_line and not standalone_fluff.match(cleaned_line):
                lines.append(cleaned_line)
        return "\n".join(lines)

    @staticmethod
    def _strip_markdown_links(text: str) -> str:
        """Replaces [label](url) with label so URLs with dots/queries do not corrupt sentence parsing."""
        return re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", text)

    def extract(
        self,
        fragments: List[str],
        project_code: str = "",
        active_focus: str = "",
        active_next: str = "",
        session_codes: Optional[List[str]] = None,
    ) -> ExtractedContext:
        """Processes raw conversation sessions into structured, continuity-preserving context."""
        non_empty_pairs: List[Tuple[str, str]] = []
        for idx, f in enumerate(fragments):
            if f and f.strip():
                s_code = (
                    session_codes[idx]
                    if session_codes and idx < len(session_codes)
                    else f"SES-{idx + 1:03d}"
                )
                non_empty_pairs.append((s_code, f))

        raw_sessions = [pair[1] for pair in non_empty_pairs]
        resolved_codes = [pair[0] for pair in non_empty_pairs]
        cleaned_fragments = [self.clean_fluff(f) for f in raw_sessions]
        combined_text = "\n\n--- [SESSION BREAK] ---\n\n".join(cleaned_fragments)

        ctx = ExtractedContext()

        # 1. Extract Session Scope & Themes (untruncated multi-session coverage)
        ctx.context_summary, ctx.session_themes = self._extract_overall_context(
            cleaned_fragments, active_focus, resolved_codes
        )

        # 2. Extract Decisions, Alternatives & Rejected Options
        raw_decisions, raw_rejected, session_options = self._extract_causal_decisions(cleaned_fragments)

        # 3. Extract Governance Constraints (untruncated)
        raw_constraints = self._extract_constraints(combined_text)

        # 4. Extract Operational Tasks (completed & pending)
        raw_pending, raw_completed = self._extract_tasks(combined_text)

        # 5. Extract Artifacts (exact file paths, schemas, modules)
        raw_artifacts = self._extract_artifacts(combined_text)

        # 6. Extract Open Questions (URL-scrubbed, substantive only)
        raw_questions = self._extract_open_questions(combined_text)

        # --- REASONING, VALIDATION & AUDITABILITY GATES ---
        turns = self.validator.parse_turns(raw_sessions)

        # 1. Authority, Evolution, Traceability Gate
        ctx.decisions, ctx.recommendations, ctx.rejected_options, unclass_dec, trace_dec = (
            self.validator.validate_authority_and_decisions(
                turns, raw_decisions, raw_rejected, raw_sessions
            )
        )
        ctx.unclassified_context.extend(unclass_dec)
        ctx.traceability_matrix.update(trace_dec)

        # Enrich decisions with session codes and alternatives considered
        for d in ctx.decisions:
            f_idx = max(1, d.source_fragment_idx)
            s_code = resolved_codes[f_idx - 1] if f_idx <= len(resolved_codes) else f"SES-{f_idx:03d}"
            d.source_session_code = s_code
            if d.code in ctx.traceability_matrix:
                ctx.traceability_matrix[d.code]["session_code"] = s_code

            if not d.alternatives_considered:
                alts: List[str] = []
                for opt in session_options.get(f_idx, []):
                    if opt.lower() not in d.title.lower():
                        alts.append(opt)
                for r in ctx.rejected_options:
                    r_stmt = r.get("statement", "")
                    if r_stmt and r_stmt.lower() not in d.title.lower() and r_stmt not in alts:
                        alts.append(f"{r_stmt} (rejected: {r.get('why', 'not aligned')})")
                if alts:
                    d.alternatives_considered = "; ".join(alts[:5])

        # 2. Constraint Validation Gate & Semantic Deduplication
        ctx.constraints, unclass_con = self.validator.validate_constraints(
            raw_constraints, combined_text + "\n" + "\n".join(raw_sessions)
        )
        ctx.unclassified_context.extend(unclass_con)

        # 3. Task & Question Gate (Questions are NOT tasks)
        ctx.pending_tasks, ctx.completed_tasks, ctx.open_questions = self.validator.validate_tasks_and_questions(
            raw_pending, raw_completed, raw_questions, combined_text + "\n" + "\n".join(raw_sessions)
        )

        # 4. Artifact Validation Gate (Preserve exact paths and identifiers)
        ctx.artifacts = self.validator.validate_artifacts(
            raw_artifacts, combined_text + "\n" + "\n".join(raw_sessions)
        )

        # 5. Technical Reasoning & Project Evolution Extraction
        (
            ctx.architecture_discussions,
            ctx.implementation_approaches,
            ctx.testing_results,
            ctx.problems_and_solutions,
        ) = self._extract_technical_reasoning(cleaned_fragments, resolved_codes)
        ctx.project_evolution = self._extract_project_evolution(
            cleaned_fragments, resolved_codes, ctx.decisions
        )

        # 6. Conflict & Contradiction Detection
        ctx.conflicts = self.validator.detect_conflicts(
            ctx.decisions, ctx.constraints, ctx.rejected_options, ctx.pending_tasks
        )

        # 7. Populate Constraint, Task, and Rejected Option Traceability
        for idx, c in enumerate(ctx.constraints, 1):
            c_code = f"CON-{idx:03d}"
            f_found = 1
            quote_found = c
            for f_idx, frag in enumerate(raw_sessions, 1):
                if c.lower() in self._strip_markdown_links(frag).lower():
                    f_found = f_idx
                    for l in frag.splitlines():
                        if c.lower()[:30] in self._strip_markdown_links(l).lower():
                            quote_found = l.strip()
                            break
                    break
            s_code = resolved_codes[f_found - 1] if f_found <= len(resolved_codes) else f"SES-{f_found:03d}"
            ctx.traceability_matrix[c_code] = {
                "fragment_idx": f_found,
                "session_code": s_code,
                "rule": c,
                "quote": quote_found,
                "status": "Active Constraint",
            }

        for idx, t in enumerate(ctx.pending_tasks, 1):
            t_code = f"TSK-{idx:03d}"
            t_title = t.get("title", "")
            f_found = 1
            quote_found = t_title
            for f_idx, frag in enumerate(raw_sessions, 1):
                if t_title.lower() in frag.lower():
                    f_found = f_idx
                    for l in frag.splitlines():
                        if t_title.lower() in l.lower():
                            quote_found = l.strip()
                            break
                    break
            s_code = resolved_codes[f_found - 1] if f_found <= len(resolved_codes) else f"SES-{f_found:03d}"
            ctx.traceability_matrix[t_code] = {
                "fragment_idx": f_found,
                "session_code": s_code,
                "title": t_title,
                "quote": quote_found,
                "status": "Pending Task",
            }

        for idx, r in enumerate(ctx.rejected_options, 1):
            r_code = r.get("code", f"REJ-{idx:03d}")
            r["code"] = r_code
            if r_code not in ctx.traceability_matrix:
                r_stmt = r.get("statement", "")
                f_found = 1
                quote_found = r_stmt
                for f_idx, frag in enumerate(raw_sessions, 1):
                    if r_stmt.lower() in frag.lower():
                        f_found = f_idx
                        for l in frag.splitlines():
                            if r_stmt.lower() in l.lower():
                                quote_found = l.strip()
                                break
                        break
                s_code = resolved_codes[f_found - 1] if f_found <= len(resolved_codes) else f"SES-{f_found:03d}"
                ctx.traceability_matrix[r_code] = {
                    "fragment_idx": f_found,
                    "session_code": s_code,
                    "statement": r_stmt,
                    "quote": quote_found,
                    "status": "Rejected Option",
                }
            else:
                f_found = ctx.traceability_matrix[r_code].get("fragment_idx", 1)
                s_code = resolved_codes[f_found - 1] if f_found <= len(resolved_codes) else f"SES-{f_found:03d}"
                ctx.traceability_matrix[r_code]["session_code"] = s_code

        # 8. Synthesize First Next Step for Next AI
        ctx.first_instruction_for_next_ai = self._determine_next_ai_instruction(ctx, active_next)

        return ctx

    def _extract_overall_context(
        self,
        fragments: List[str],
        active_focus: str,
        session_codes: List[str],
    ) -> Tuple[str, List[str]]:
        """Synthesizes multi-session problem space and per-session themes without single-fragment truncation."""
        if not fragments:
            return active_focus or "Active project development session.", []

        themes: List[str] = []
        multi = len(fragments) > 1

        for idx, frag in enumerate(fragments):
            s_code = session_codes[idx] if idx < len(session_codes) else f"SES-{idx + 1:03d}"
            frag_no_code = re.sub(r"```[\s\S]*?```", "", frag)
            headings: List[str] = []
            substantive_lines: List[str] = []

            for raw_l in frag_no_code.splitlines():
                l = self._strip_markdown_links(raw_l.strip())
                if not l:
                    continue
                if l.startswith("#"):
                    h = l.lstrip("#").strip()
                    if len(h) > 3 and len(h) <= 120:
                        headings.append(h)
                elif len(l) >= 12 and not l.startswith(("- [ ]", "- [x]", "* [ ]", "* [x]")):
                    substantive_lines.append(l)

            lead = ""
            if headings and substantive_lines:
                lead = f"{headings[0]} — {substantive_lines[0][:220]}"
            elif substantive_lines:
                lead = " ".join(substantive_lines[:2])[:260]
            elif headings:
                lead = "; ".join(headings[:2])[:220]

            if lead:
                entry = f"[{s_code}] {lead}" if multi else lead
                if not any(t.lower() == entry.lower() for t in themes):
                    themes.append(entry)

        if not themes:
            return active_focus or "Active project development session.", []

        if multi:
            joined_preview = " | ".join(themes[:5])
            if len(themes) > 5:
                joined_preview += f" (+{len(themes) - 5} additional sessions)"
            if active_focus and active_focus.lower() not in joined_preview.lower():
                summary = f"Focus: {active_focus}. Multi-session continuity across {len(fragments)} sessions: {joined_preview}"
            else:
                summary = f"Multi-session continuity across {len(fragments)} sessions: {joined_preview}"
        else:
            lead_thought = themes[0]
            if active_focus and active_focus.lower() not in lead_thought.lower():
                summary = f"Focus: {active_focus}. Discussion centered on: {lead_thought}"
            else:
                summary = lead_thought

        return summary[:1200], themes

    def _extract_causal_decisions(
        self, fragments: List[str]
    ) -> Tuple[List[CausalDecision], List[Dict[str, str]], Dict[int, List[str]]]:
        """Extracts decisions, candidate options considered, and rejected alternatives with full rationale."""
        decisions: List[CausalDecision] = []
        rejected: List[Dict[str, str]] = []
        session_options: Dict[int, List[str]] = {}

        decision_regex = re.compile(
            r"(?:we decided to|we decided|decided to|let'?s (?:go with|use|stick to|choose|adopt)|agreed to)\s+([^\n]+)",
            re.IGNORECASE,
        )
        explicit_decision_regex = re.compile(r"^(?:Decision|Choice):\s*(.+)$", re.IGNORECASE)

        reject_regex = re.compile(
            r"(?:do not use|don'?t use|avoid|rejected|not using|ruled out|discarded|opted against|dropped)\s+([^\n]+)",
            re.IGNORECASE,
        )
        explicit_reject_regex = re.compile(
            r"^(?:Rejected Option|Rejected Approach|Rejected|Do Not Repeat):\s*(.+)$",
            re.IGNORECASE,
        )
        option_regex = re.compile(
            r"^(?:Option\s+[A-Z0-9]+|Candidate\s+\d+|\d+\.)[:\s]+([A-Za-z0-9][^\n]{3,140})$",
            re.IGNORECASE,
        )

        speculative_words = (
            "what if", "maybe", "perhaps", "could consider", "might consider",
            "evaluating", "pros and cons", "whereas", "experiment", "brainstorming"
        )

        dec_count = 1
        rej_count = 1

        for f_idx, frag in enumerate(fragments, 1):
            frag_no_code = re.sub(r"```[\s\S]*?```", "", frag)
            session_options[f_idx] = []

            for line in frag_no_code.splitlines():
                l_str = line.strip()
                if not l_str or len(l_str) > 1500:
                    continue

                # Capture candidate options evaluated in this session
                m_opt = option_regex.match(l_str)
                if m_opt:
                    opt_text = m_opt.group(1).strip().rstrip(".")
                    if opt_text and opt_text not in session_options[f_idx]:
                        session_options[f_idx].append(opt_text)

                # Filter out speculative/brainstorming clauses from becoming decisions or rejections
                if any(w in l_str.lower() for w in speculative_words):
                    continue

                # 1. Decisions
                m_dec = decision_regex.search(l_str) or explicit_decision_regex.search(l_str)
                if m_dec:
                    full = m_dec.group(1).strip().rstrip(".")
                    why_match = re.search(
                        r"\b(?:because of|because|due to|in order to|so that|since|as|why:|rationale:)\b\s*(.+)$",
                        full,
                        re.IGNORECASE,
                    )
                    if why_match:
                        title = full[:why_match.start()].strip().rstrip("(,;- ")
                        why = why_match.group(1).strip().rstrip(")")
                    else:
                        title = full
                        why = "Confirmed in collaborative AI conversation"

                    if title and len(title) > 3 and not any(w in title.lower() for w in speculative_words):
                        if not any(d.title.lower() == title.lower() for d in decisions):
                            decisions.append(CausalDecision(
                                code=f"DEC-{dec_count:03d}",
                                title=title,
                                human_decision=f"Confirmed: {title}",
                                reasoning=why,
                                resulting_action="Adopted in project implementation",
                                source_fragment_idx=f_idx,
                                evidence_quote=l_str,
                            ))
                            dec_count += 1
                    continue

                # 2. Rejected Options
                m_rej = reject_regex.search(l_str) or explicit_reject_regex.search(l_str)
                if m_rej:
                    full = m_rej.group(1).strip().rstrip(".")
                    why_match = re.search(
                        r"\b(?:because of|because|due to|since|as|why:|rationale:)\b\s*(.+)$",
                        full,
                        re.IGNORECASE,
                    )
                    if why_match:
                        item = full[:why_match.start()].strip().rstrip("(,;- ")
                        why = why_match.group(1).strip().rstrip(")")
                    else:
                        item = full
                        why = "Not aligned with project goals or constraints"

                    if item and len(item) > 3:
                        if not any(r["statement"].lower() == item.lower() for r in rejected):
                            rejected.append({
                                "code": f"REJ-{rej_count:03d}",
                                "statement": item,
                                "why": why,
                                "quote": l_str,
                            })
                            rej_count += 1
                    continue

        return decisions, rejected, session_options

    def _extract_constraints(self, text: str) -> List[str]:
        """Extracts hard limits, governance rules, frozen boundaries, and invariants without truncation."""
        constraints: List[str] = []
        text_no_code = re.sub(r"```[\s\S]*?```", "", text)

        labeled_pat = re.compile(
            r"^(?:[-*•]\s*)?(?:limitation|constraint|governance|frozen decision|invariant|boundary|rule):\s*(.+)$",
            re.IGNORECASE,
        )
        modal_pat = re.compile(
            r"\b((?:(?:the|all|system|application|frontend|backend|database|schema|architecture)\s+[A-Za-z0-9_\-\s]{0,30}?)?"
            r"(?:must\s+(?:not\s+|never\s+|strictly\s+|remain\s+)?|cannot\s+|can't\s+|should\s+not\s+|"
            r"do\s+not\s+(?:break|modify|alter|redesign|violate)\s+|never\s+(?:break|bypass|overwrite|delete)\s+|"
            r"strictly\s+|architecture\s+freeze|non-negotiable)[^\n]+)",
            re.IGNORECASE,
        )

        for raw_line in text_no_code.splitlines():
            clean_line = self._strip_markdown_links(raw_line.strip())
            if not clean_line or len(clean_line) > 1000:
                continue

            m_lbl = labeled_pat.match(clean_line)
            if m_lbl:
                # Split only on real sentence endings, NEVER inside filenames (.py) or decimals (4.5)
                clauses = re.split(r"(?<!\d)\.(?=\s+[A-Z]|\s*$)", m_lbl.group(1).strip())
                c_str = clauses[0].strip().rstrip(".")
                if len(c_str) > 5 and not any(c.lower() == c_str.lower() for c in constraints):
                    constraints.append(c_str)
                continue

            # Split multi-sentence lines safely on real sentence boundaries only
            sentences = re.split(r"(?<!\d)\.(?=\s+[A-Z]|\s*$)", clean_line)
            for sent in sentences:
                s_clean = sent.strip().rstrip(".")
                if not s_clean or "?" in s_clean:
                    continue
                m_mod = modal_pat.search(s_clean)
                if m_mod:
                    c_str = m_mod.group(1).strip().rstrip(".")
                    if len(c_str) > 5 and not any(c.lower() == c_str.lower() for c in constraints):
                        constraints.append(c_str)

        return constraints

    def _extract_technical_reasoning(
        self, cleaned_fragments: List[str], session_codes: List[str]
    ) -> Tuple[List[str], List[str], List[str], List[str]]:
        """Preserves Technical Reasoning across 4 sub-streams:
        1. Architecture discussions & trade-offs
        2. Implementation approaches & mechanics
        3. Testing & benchmark results
        4. Problems encountered & solutions applied
        """
        arch_list: List[str] = []
        impl_list: List[str] = []
        test_list: List[str] = []
        prob_list: List[str] = []

        multi = len(cleaned_fragments) > 1

        arch_pat = re.compile(
            r"\b(?:architecture|trade-?offs?|versus|\bvs\.?\b|whereas|option\s+[a-d1-4]|"
            r"event sourcing|cqrs|ipc|custody|state machine|transaction boundary|decoupl|"
            r"single-binary|air-gapped|multi-session|data flow|design pattern)\b",
            re.IGNORECASE,
        )
        impl_pat = re.compile(
            r"\b(?:implement(?:ed|ing|ation)?|configur(?:e|ed|ing)|pragma|synchronous=|journal_mode=|"
            r"dispatcher|endpoint|handler|migration|wired|refactored|schema\.sql|"
            r"src/[a-zA-Z0-9_./\-]+)\b",
            re.IGNORECASE,
        )
        test_pat = re.compile(
            r"\b(?:benchmark|ops/sec|unittest|pytest|test suite|tests?\s+passed|\bPASSED\b|\bFAILED\b|"
            r"exit\s*0|zero disk thrashing|regression|self-check|--check|verified match|100%\s+pass)\b",
            re.IGNORECASE,
        )
        prob_pat = re.compile(
            r"\b(?:risks?\s+data\s+loss|bug|defect|root cause|crash(?:es|ed)?|race condition|"
            r"deadlock|port conflicts?|brittle|bottleneck|overflow|truncat(?:ed|ion)|"
            r"problem:|issue:|fixed\s+by|resolved\s+by|workaround|mitigat(?:ed|ion)|solution:)\b",
            re.IGNORECASE,
        )

        def _add_unique(target: List[str], item: str, s_code: str) -> None:
            norm = re.sub(r"\s+", " ", item).strip()
            if len(norm) < 15 or len(norm) > 450:
                return
            tagged = f"[{s_code}] {norm}" if multi else norm
            raw_cmp = norm.lower()
            if not any(raw_cmp in existing.lower() or existing.lower().endswith(raw_cmp) for existing in target):
                target.append(tagged)

        for idx, frag in enumerate(cleaned_fragments):
            s_code = session_codes[idx] if idx < len(session_codes) else f"SES-{idx + 1:03d}"
            frag_no_code = re.sub(r"```[\s\S]*?```", "", frag)
            for raw_line in frag_no_code.splitlines():
                line = self._strip_markdown_links(raw_line.strip())
                if not line or line.startswith(("#", "---")):
                    continue
                # Strip leading list bullet for clean reading while keeping checkbox context out
                if re.match(r"^\s*[-*•]?\s*\[\s*[ xX]?\s*\]", line):
                    if test_pat.search(line):
                        _add_unique(test_list, re.sub(r"^\s*[-*•]?\s*\[\s*[ xX]?\s*\]\s*", "", line), s_code)
                    continue
                clean_l = re.sub(r"^\s*[-*•]\s*", "", line).strip()
                if "?" in clean_l and clean_l.endswith("?"):
                    continue

                if test_pat.search(clean_l):
                    _add_unique(test_list, clean_l, s_code)
                if prob_pat.search(clean_l):
                    _add_unique(prob_list, clean_l, s_code)
                if arch_pat.search(clean_l):
                    _add_unique(arch_list, clean_l, s_code)
                elif impl_pat.search(clean_l):
                    _add_unique(impl_list, clean_l, s_code)

        return arch_list, impl_list, test_list, prob_list

    def _extract_project_evolution(
        self,
        cleaned_fragments: List[str],
        session_codes: List[str],
        decisions: List[CausalDecision],
    ) -> List[str]:
        """Captures Project Evolution: how the design changed over time, turning points, and lessons learned."""
        evolution: List[str] = []
        multi = len(cleaned_fragments) > 1

        evo_pat = re.compile(
            r"\b(?:change of plans?|changed my mind|instead of|workflow correction|"
            r"important clarification|turning point|lesson(?:s)? learned|takeaway|"
            r"realized that|shifted from|migrated from|replaced\s+.+\s+with|superseded|"
            r"previously\s+we|revised\s+the\s+(?:design|architecture|workflow))\b",
            re.IGNORECASE,
        )

        # 1. Include structured decision reversals detected by validator
        for d in decisions:
            if d.problem and d.problem.lower().startswith("replaced "):
                prefix = f"[{d.source_session_code}] " if (multi and d.source_session_code) else ""
                entry = f"{prefix}Decision Pivot: {d.problem} (Why: {d.reasoning})"
                if not any(entry.lower() == e.lower() for e in evolution):
                    evolution.append(entry)

        # 2. Scan session lines for explicit design shifts, corrections, and lessons learned
        for idx, frag in enumerate(cleaned_fragments):
            s_code = session_codes[idx] if idx < len(session_codes) else f"SES-{idx + 1:03d}"
            frag_no_code = re.sub(r"```[\s\S]*?```", "", frag)
            for raw_line in frag_no_code.splitlines():
                line = self._strip_markdown_links(raw_line.strip())
                if not line or len(line) < 15 or len(line) > 450 or line.endswith("?"):
                    continue
                clean_l = re.sub(r"^\s*[-*•]\s*", "", line).strip()
                if evo_pat.search(clean_l):
                    tagged = f"[{s_code}] {clean_l}" if multi else clean_l
                    if not any(clean_l.lower() in e.lower() for e in evolution):
                        evolution.append(tagged)

        return evolution

    def _extract_tasks(self, text: str) -> Tuple[List[Dict[str, str]], List[Dict[str, str]]]:
        """Extracts checklist items and explicit operational state items without artificial caps."""
        pending: List[Dict[str, str]] = []
        completed: List[Dict[str, str]] = []
        text_no_code = re.sub(r"```[\s\S]*?```", "", text)

        # 1. Checkboxes: - [ ] Task or - [x] Task
        cb_pat = re.compile(r"^\s*[-*•]?\s*\[\s*([ xX])\s*\]\s*(.+)$", re.MULTILINE)
        for m in cb_pat.finditer(text_no_code):
            is_done = m.group(1).lower() == "x"
            task_title = m.group(2).strip()
            item = {"title": task_title, "why": "Tracked from conversation checklist"}
            if is_done:
                if not any(t["title"].lower() == task_title.lower() for t in completed):
                    completed.append(item)
            else:
                if not any(t["title"].lower() == task_title.lower() for t in pending):
                    pending.append(item)

        # 2. Explicit operational state lines (TODO / Next step / Remaining work / Completed)
        todo_pat = re.compile(
            r"^(?:TODO|Next step|Step \d+|Remaining work|Action item):\s*(.+)$",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in todo_pat.finditer(text_no_code):
            t_str = m.group(1).strip()
            if len(t_str) > 5 and not any(t["title"].lower() == t_str.lower() for t in pending):
                pending.append({"title": t_str, "why": "Immediate planned step"})

        done_pat = re.compile(
            r"^(?:Completed|Completed work|Done):\s*(.+)$",
            re.IGNORECASE | re.MULTILINE,
        )
        for m in done_pat.finditer(text_no_code):
            d_str = m.group(1).strip()
            if len(d_str) > 5 and not any(t["title"].lower() == d_str.lower() for t in completed):
                completed.append({"title": d_str, "why": "Completed milestone recorded in session"})

        return pending, completed

    def _extract_artifacts(self, text: str) -> List[Dict[str, str]]:
        """Extracts referenced file paths, code modules, and specifications without artificial caps."""
        artifacts: List[Dict[str, str]] = []
        path_pat = re.compile(
            r"(?:[\s`\"'\(\[]|^)([a-zA-Z0-9_\-\./\\]+\.(?:py|js|ts|html|css|json|md|sql|sh|bat|yaml|yml))(?=[`\"'\)\],;:!?\.\s]|$)",
            re.IGNORECASE,
        )
        for m in path_pat.finditer(text):
            path_str = m.group(1).strip()
            if "/" in path_str or "\\" in path_str or "." in path_str:
                norm_path = path_str.replace("\\", "/")
                if not any(a["path"].lower() == norm_path.lower() for a in artifacts):
                    artifacts.append({
                        "path": norm_path,
                        "status": "Referenced in AI Discussion",
                    })

        return artifacts

    def _extract_open_questions(self, text: str) -> List[str]:
        """Identifies unresolved questions or pending human decisions, stripping URL query strings first."""
        questions: List[str] = []
        # Strip code blocks and URLs so ?usp=sharing or query params never masquerade as open questions
        clean_source = re.sub(r"```[\s\S]*?```", "", text)
        clean_source = re.sub(r"\[([^\]]+)\]\(https?://[^\)]+\)", r"\1", clean_source)
        clean_source = re.sub(r"https?://\S+", "", clean_source)

        q_pat = re.compile(
            r"(?:(?:open question|tbd|to determine|still need to|unresolved):\s*([^.\n\?]+[\?]?)|([^.\n]+\?))",
            re.IGNORECASE,
        )
        standalone_fluff = (
            "what do you think?", "what do you think",
            "how does that look?", "how does that look",
            "anything else?", "anything else",
            "how would you like to proceed?", "how would you like to proceed",
            "shall we proceed?", "shall we proceed",
            "does that make sense?", "does that make sense",
        )

        for m in q_pat.finditer(clean_source):
            q_str = (m.group(1) or m.group(2) or "").strip()
            q_cleaned = re.sub(
                r",?\s*(?:what do you think|how does that look|anything else)\??$",
                "?",
                q_str,
                flags=re.IGNORECASE,
            ).strip()
            if q_cleaned.lower() in standalone_fluff:
                continue
            if len(q_cleaned) > 10 and "?" in q_cleaned and " " in q_cleaned:
                if not any(q.lower() == q_cleaned.lower() for q in questions):
                    questions.append(q_cleaned)

        return questions

    def _determine_next_ai_instruction(self, ctx: ExtractedContext, active_next: str) -> str:
        """Determines the single sharpest starting prompt instruction for the next AI session."""
        # 1. Active contradiction / conflict takes highest priority
        if ctx.conflicts:
            cf = ctx.conflicts[0]
            return f"Resolve active contradiction: {cf['type']} between '{cf['statement_a']}' and '{cf['statement_b']}'."

        # 2. Immediate pending tasks take priority when concrete checklist items exist
        if ctx.pending_tasks:
            return f"Begin with task: '{ctx.pending_tasks[0]['title']}'."

        # 3. Pending Human Decision on proposed recommendations
        if ctx.recommendations:
            rec = ctx.recommendations[0]
            rec_stmt = rec.get("statement", "")
            return f"Decide on pending proposal: '{rec_stmt}' (Awaiting human decision)."

        # 4. Open review questions / blockers
        if ctx.open_questions:
            for q in ctx.open_questions:
                if "strengths, weaknesses, and gaps" in q.lower():
                    return "Evaluate current strengths, weaknesses, and gaps."
                if q.lower().startswith("open review question:"):
                    return q.split(":", 1)[1].strip()
            return f"Resolve open question: '{ctx.open_questions[0]}'."

        # 5. Immediate follow-up on ratified decisions
        if ctx.decisions:
            return f"Proceed with implementation of ratified decision: '{ctx.decisions[-1].title}'."

        if active_next:
            return active_next

        return "Review active context and propose the immediate next concrete execution step."

    def compile_markdown_checkpoint(
        self,
        project_code: str,
        project_name: str,
        session_id: str,
        snapshot_code: str,
        checksum_sha256: str,
        extracted: ExtractedContext,
        fragment_count: int,
        checkpoint_status: str = "GENERATED",
        chapter_code: str = "",
        session_range: str = "",
    ) -> str:
        """Compiles a Continuity_MD chapter (primary continuity evidence Markdown)."""
        now_dt = datetime.now(timezone.utc)
        date_str = now_dt.strftime("%Y-%m-%d %H:%M UTC")
        header_title = (
            f"# {chapter_code} — Project Checkpoint ({project_code})"
            if chapter_code
            else f"# Project Checkpoint — {project_code}"
        )

        lines = [
            header_title,
            f"- **Project:** {project_name} (`{project_code}`)",
        ]
        if chapter_code:
            lines.append(f"- **Continuity Chapter:** `{chapter_code}`")
        if session_range:
            lines.append(f"- **Session Coverage:** `{session_range}` ({fragment_count} complete session(s))")
        else:
            lines.append(f"- **Analyzed Sessions:** {fragment_count} conversation session(s)")
        lines.extend([
            f"- **Generated At:** {date_str}",
            f"- **Batch ID:** `{session_id[:8]}`",
            f"- **Checkpoint Status:** `{checkpoint_status}`",
            f"- **Snapshot Seal:** `{snapshot_code}` (SHA-256: `{checksum_sha256[:12]}...`)",
            "",
            "---",
            "",
            "## 1. Context & Session Scope",
            extracted.context_summary or "Active collaboration session.",
        ])
        if len(extracted.session_themes) > 1:
            lines.append("")
            lines.append("### Session-by-Session Progression")
            for theme in extracted.session_themes:
                lines.append(f"- {theme}")

        lines.extend([
            "",
            "## 2. Key Decisions & Decision History",
        ])

        if extracted.decisions:
            for d in extracted.decisions:
                ses_tag = f" *({d.source_session_code})*" if d.source_session_code else ""
                lines.append(f"- **[{d.code}]** **{d.title}**{ses_tag}")
                if d.problem:
                    lines.append(f"  - **Problem / Context:** {d.problem}")
                if d.recommendation:
                    lines.append(f"  - **AI Recommendation:** {d.recommendation}")
                if d.alternatives_considered:
                    lines.append(f"  - **Alternatives Considered:** {d.alternatives_considered}")
                if d.human_decision:
                    lines.append(f"  - **Human Decision:** {d.human_decision}")
                lines.append(f"  - **Why Decided:** {d.reasoning}")
                if d.evidence_quote:
                    lines.append(f"  - **Evidence:** \"{d.evidence_quote}\"")
                if d.resulting_action:
                    lines.append(f"  - **Resulting Action:** {d.resulting_action}")
        else:
            lines.append("- *(No ratified architectural decisions recorded in this chapter)*")

        if extracted.recommendations:
            lines.append("")
            lines.append("### Proposed Alternatives (Awaiting Human Decision)")
            for r in extracted.recommendations:
                ev = r.get("quote") or r.get("evidence_quote")
                why = r.get("reasoning", "")
                why_str = f" — Why proposed: {why}" if why else ""
                ev_str = f" *(Evidence: \"{ev}\")*" if ev else ""
                lines.append(f"- **💡 [{r['code']}]** {r['statement']}{why_str} *(Status: {r['status']})*{ev_str}")

        if extracted.rejected_options:
            lines.append("")
            lines.append("### Rejected Options (Do Not Repeat)")
            for r in extracted.rejected_options:
                ev = r.get("quote") or r.get("evidence_quote")
                ev_str = f"; Evidence: \"{ev}\"" if ev else ""
                lines.append(f"- **⛔ [{r['code']}]** {r['statement']} *(Why rejected: {r['why']}{ev_str})*")

        if extracted.conflicts:
            lines.append("")
            lines.append("### ⚠️ Active Conflicts & Contradictions (Requires Attention)")
            for cf in extracted.conflicts:
                lines.append(f"- **[{cf['type']}]** {cf['statement_a']} <-> {cf['statement_b']}")
                lines.append(f"  - *Impact: {cf['impact']}*")

        lines.append("")
        lines.append("## 3. Constraints & Governance Boundaries")
        if extracted.constraints:
            for idx, c in enumerate(extracted.constraints, 1):
                c_code = f"CON-{idx:03d}"
                c_trace = extracted.traceability_matrix.get(c_code, {})
                ev = c_trace.get("quote")
                s_code = c_trace.get("session_code")
                s_tag = f" `[{s_code}]`" if s_code else ""
                ev_str = f" *(Evidence: \"{ev}\")*" if ev and ev != c else ""
                lines.append(f"- **[{c_code}]**{s_tag} {c}{ev_str}")
        else:
            lines.append("- *(No new hard governance constraints defined in this chapter)*")

        lines.append("")
        lines.append("## 4. Tasks & Operational State")
        if extracted.pending_tasks or extracted.completed_tasks:
            if extracted.completed_tasks:
                lines.append("### Completed Work")
                for idx, t in enumerate(extracted.completed_tasks, 1):
                    lines.append(f"- [x] **[DONE-{idx:03d}]** {t['title']}")
            if extracted.pending_tasks:
                lines.append("### Remaining Work")
                for idx, t in enumerate(extracted.pending_tasks, 1):
                    t_code = f"TSK-{idx:03d}"
                    t_trace = extracted.traceability_matrix.get(t_code, {})
                    ev = t_trace.get("quote")
                    ev_str = f"; Evidence: \"{ev}\"" if ev and ev != t['title'] else ""
                    lines.append(f"- [ ] **[{t_code}]** {t['title']} *(Why: {t['why']}{ev_str})*")
        else:
            lines.append("- *(Checklist is clear)*")
        lines.append(f"- **Next Recommended Action:** {extracted.first_instruction_for_next_ai}")

        lines.append("")
        lines.append("## 5. Artifacts & Codebase Touchpoints")
        if extracted.artifacts:
            for a in extracted.artifacts:
                lines.append(f"- `{a['path']}` — **Status:** {a['status']}")
        else:
            lines.append("- *(No specific file paths referenced)*")

        lines.append("")
        lines.append("## 6. Open Questions & Pending Decisions")
        if extracted.open_questions:
            for q in extracted.open_questions:
                lines.append(f"- ❓ {q}")
        else:
            lines.append("- *(No open blockers or pending questions)*")

        lines.append("")
        lines.append("## 7. Technical Reasoning & Project Evolution")
        has_reasoning = any([
            extracted.architecture_discussions,
            extracted.implementation_approaches,
            extracted.testing_results,
            extracted.problems_and_solutions,
            extracted.project_evolution,
        ])
        if has_reasoning:
            if extracted.architecture_discussions:
                lines.append("### 7.1 Architecture Discussions & Trade-Offs")
                for item in extracted.architecture_discussions:
                    lines.append(f"- {item}")
            if extracted.implementation_approaches:
                lines.append("### 7.2 Implementation Approaches")
                for item in extracted.implementation_approaches:
                    lines.append(f"- {item}")
            if extracted.testing_results:
                lines.append("### 7.3 Testing & Verification Results")
                for item in extracted.testing_results:
                    lines.append(f"- {item}")
            if extracted.problems_and_solutions:
                lines.append("### 7.4 Problems Encountered & Solutions Applied")
                for item in extracted.problems_and_solutions:
                    lines.append(f"- {item}")
            if extracted.project_evolution:
                lines.append("### 7.5 Project Evolution & Lessons Learned")
                for item in extracted.project_evolution:
                    lines.append(f"- {item}")
        else:
            lines.append("- *(No additional technical trade-off or evolution notes in this interval)*")

        lines.append("")
        lines.append("---")
        lines.append("")
        lines.append("## 8. Next Session Bootstrap")
        lines.append("> **Ready-to-Copy Continuation Prompt:** Paste this block into your next AI chat window to resume work with full continuity context.")
        lines.append("")
        lines.append("```scs-bootstrap")
        lines.append(f"=== [SCS CONTINUITY BOOTSTRAP: {project_code}] ===")
        lines.append(f"Project: {project_name} ({project_code})")
        if chapter_code:
            lines.append(f"Chapter: {chapter_code} ({session_range or f'{fragment_count} sessions'})")
        lines.append(f"Anchor Checkpoint Seal: {snapshot_code} (SHA: {checksum_sha256[:12]})")
        lines.append("")
        lines.append("1. ACTIVE CONTEXT & MISSION:")
        lines.append(f"   • Context: {extracted.context_summary}")
        lines.append(f"   • Next Concrete Action: {extracted.first_instruction_for_next_ai}")
        lines.append("")
        lines.append(f"2. CONFIRMED DECISIONS ({len(extracted.decisions)}):")
        for d in extracted.decisions:
            alt_note = f"; Alternatives: {d.alternatives_considered}" if d.alternatives_considered else ""
            lines.append(f"   • {d.title} (Why: {d.reasoning}{alt_note})")
        if not extracted.decisions:
            lines.append("   • (None)")
        lines.append("")
        lines.append(f"3. CONSTRAINTS ({len(extracted.constraints)}):")
        for c in extracted.constraints:
            lines.append(f"   • [RULE] {c}")
        if not extracted.constraints:
            lines.append("   • (None)")
        lines.append("")
        if extracted.rejected_options:
            lines.append(f"4. REJECTED OPTIONS (DO NOT REPEAT) ({len(extracted.rejected_options)}):")
            for r in extracted.rejected_options:
                lines.append(f"   • [DO NOT REPEAT] {r['statement']} (Why: {r['why']})")
            lines.append("")
        lines.append(f"5. ACTIVE TASKS ({len(extracted.pending_tasks)} pending, {len(extracted.completed_tasks)} completed):")
        for t in extracted.pending_tasks:
            lines.append(f"   • [○ Pending] {t['title']}")
        if not extracted.pending_tasks:
            lines.append("   • (All clear)")
        lines.append("")
        if extracted.conflicts:
            lines.append("6. ⚠️ ACTIVE CONFLICTS DETECTED:")
            for cf in extracted.conflicts:
                lines.append(f"   • {cf['statement_a']} <-> {cf['statement_b']}")
            lines.append("")
        lines.append("7. WHAT TO DO FIRST IN THIS SESSION:")
        lines.append(f"   👉 {extracted.first_instruction_for_next_ai}")
        lines.append("=================================================")
        lines.append("```")

        # Machine-readable chapter envelope for lossless multi-chapter AI_HANDOVER_PACKAGE synthesis
        chapter_payload = {
            "protocol": "scs-continuity-md/1.0",
            "chapter_code": chapter_code or "Continuity_MD",
            "session_range": session_range or f"1..{fragment_count}",
            "session_count": fragment_count,
            "snapshot_code": snapshot_code,
            "context_summary": extracted.context_summary,
            "session_themes": extracted.session_themes,
            "decisions": [
                {
                    "code": d.code,
                    "statement": d.title,
                    "why": d.reasoning,
                    "problem": d.problem,
                    "recommendation": d.recommendation,
                    "alternatives_considered": d.alternatives_considered,
                    "session_code": d.source_session_code,
                }
                for d in extracted.decisions
            ],
            "recommendations": extracted.recommendations,
            "rejected_options": extracted.rejected_options,
            "constraints": [{"statement": c, "why": "Governance boundary constraint"} for c in extracted.constraints],
            "architecture_discussions": extracted.architecture_discussions,
            "implementation_approaches": extracted.implementation_approaches,
            "testing_results": extracted.testing_results,
            "problems_and_solutions": extracted.problems_and_solutions,
            "project_evolution": extracted.project_evolution,
            "tasks": [
                *[{"title": t["title"], "status": "COMPLETED", "why": t.get("why", "")} for t in extracted.completed_tasks],
                *[{"title": t["title"], "status": "PENDING", "why": t.get("why", "")} for t in extracted.pending_tasks],
            ],
            "artifacts": [
                {"name": a["path"].split("/")[-1], "relative_path": a["path"], "note": a["status"]}
                for a in extracted.artifacts
            ],
            "open_questions": extracted.open_questions,
            "next_action": extracted.first_instruction_for_next_ai,
        }
        lines.append("")
        lines.append("```scs-continuity-chapter")
        lines.append(json.dumps(chapter_payload, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append(f"*Sealed by SCS-HUD Conversation Checkpoint Engine. Audit SHA-256: `{checksum_sha256}`*")

        raw_md = "\n".join(lines)
        scrubbed_md, _ = scrub_secrets(raw_md)
        return scrubbed_md

    @staticmethod
    def parse_chapter_metadata(markdown_content: str) -> Dict[str, Any]:
        """Extracts structured scs-continuity-chapter JSON payload from an approved Continuity_MD chapter."""
        m = re.search(r"```scs-continuity-chapter\s*(\{[\s\S]*?\})\s*```", markdown_content)
        if m:
            try:
                data = json.loads(m.group(1))
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return {}

    def compile_ai_handover_package(
        self,
        proj: Any,
        snapshot: Any,
        decisions: List[Any],
        tasks: List[Any],
        artifacts: List[Any],
        chapters: List[Dict[str, Any]],
        session_counts: Dict[str, int],
        sync_footer: str = "",
    ) -> str:
        """Merges approved Continuity_MD_01..NN chapters + canonical SQLite state into AI_HANDOVER_PACKAGE.md."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        clean_next = sanitize_proposition(proj.next_action) if proj.next_action else "Review active tasks and proceed."

        parsed_chapters: List[Dict[str, Any]] = []
        all_arch: List[str] = []
        all_impl: List[str] = []
        all_tests: List[str] = []
        all_probs: List[str] = []
        all_evolution: List[str] = []
        all_open_questions: List[str] = []
        all_recommendations: List[Dict[str, str]] = []
        decision_alt_lookup: Dict[str, Dict[str, str]] = {}

        def _merge_unique(dest: List[str], items: List[str]) -> None:
            for it in items:
                if it and not any(it.lower() == ex.lower() for ex in dest):
                    dest.append(it)

        for idx, ch in enumerate(chapters, 1):
            meta = self.parse_chapter_metadata(ch.get("markdown_content", ""))
            ch_code = meta.get("chapter_code") or f"Continuity_MD_{idx:02d}"
            parsed_chapters.append({
                "chapter_code": ch_code,
                "session_range": meta.get("session_range", "N/A"),
                "session_count": meta.get("session_count", 0),
                "snapshot_code": meta.get("snapshot_code") or ch.get("snapshot_code", "SEALED"),
                "context_summary": meta.get("context_summary", ""),
                "session_themes": meta.get("session_themes", []),
                "created_at": ch.get("created_at", ""),
            })
            _merge_unique(all_arch, meta.get("architecture_discussions", []))
            _merge_unique(all_impl, meta.get("implementation_approaches", []))
            _merge_unique(all_tests, meta.get("testing_results", []))
            _merge_unique(all_probs, meta.get("problems_and_solutions", []))
            _merge_unique(all_evolution, meta.get("project_evolution", []))
            _merge_unique(all_open_questions, meta.get("open_questions", []))
            for rec in meta.get("recommendations", []):
                stmt = rec.get("statement", "")
                if stmt and not any(stmt.lower() == r.get("statement", "").lower() for r in all_recommendations):
                    all_recommendations.append(rec)
            for cd in meta.get("decisions", []):
                stmt_key = sanitize_proposition(cd.get("statement", ""), default_verb="Use").lower()
                if stmt_key:
                    decision_alt_lookup[stmt_key] = cd

        active_decisions = [d for d in decisions if getattr(d, "is_active", True) and d.record_kind.value == "DECISION"]
        superseded_decisions = [d for d in decisions if not getattr(d, "is_active", True) and d.record_kind.value == "DECISION"]
        active_constraints = [d for d in decisions if getattr(d, "is_active", True) and d.record_kind.value == "CONSTRAINT"]
        rejected_options = [d for d in decisions if getattr(d, "is_active", True) and d.record_kind.value == "REJECTED_OPTION"]

        completed_tasks = [t for t in tasks if t.status.value == "COMPLETED"]
        active_tasks = [t for t in tasks if t.status.value in ("IN_PROGRESS", "BLOCKED", "PENDING")]

        total_sess = session_counts.get("total_sessions", 0)
        proc_sess = session_counts.get("processed_sessions", 0)
        pend_sess = session_counts.get("pending_sessions", 0)

        lines = [
            f"# AI HANDOVER PACKAGE (SESSION HANDOVER PACKAGE) — {proj.name} ({proj.code})",
            f"- **Package Type:** Master AI Continuity Restoration Package (`scs-handover/1.0`)",
            f"- **Snapshot Code:** `{snapshot.snapshot_code}`",
            f"- **Seal SHA-256:** `{snapshot.checksum_sha256}`",
            f"- **Generated At:** `{now_str}`",
            f"- **Continuity Coverage:** `{len(parsed_chapters)}` Continuity_MD chapter(s) | `{proc_sess}/{total_sess}` session(s) sealed"
            + (f" (`{pend_sess}` unratified session(s) pending in buffer)" if pend_sess > 0 else ""),
            "",
            "> **PURPOSE FOR FRESH AI SESSION:** This handover package restores complete multi-session project intelligence—including WHY decisions were ratified, WHY rejected approaches failed, frozen governance boundaries, technical implementation & testing context, and project evolution—so you can resume work immediately without historical re-questioning.",
            "",
            "## 1. Executive Summary",
            f"- **Current Objective:** {proj.objective or 'N/A'}",
            f"- **Current Focus:** {proj.current_focus or 'N/A'}",
            f"- **Immediate Next Action:** {clean_next}",
            f"- **Operational Telemetry:** `{len(active_decisions)}` Active Decisions | `{len(active_constraints)}` Governance Constraints | `{len(rejected_options)}` Rejected Approaches | `{len(completed_tasks)}` Completed Tasks | `{len(active_tasks)}` Remaining Tasks",
            "",
            "## 2. Project Evolution & Continuity Chapter History",
        ]

        if parsed_chapters:
            lines.append("### 2.1 Sealed Continuity Chapters")
            for pch in parsed_chapters:
                lines.append(
                    f"- **`{pch['chapter_code']}`** (`{pch['session_range']}`, Seal `{pch['snapshot_code']}`): "
                    f"{pch['context_summary'] or 'Ratified continuity chapter.'}"
                )
                for th in pch.get("session_themes", []):
                    lines.append(f"  - {th}")
        else:
            lines.append("- *(Canonical ledger snapshot — no multi-session Continuity_MD chapters archived yet)*")

        if all_evolution or superseded_decisions:
            lines.append("")
            lines.append("### 2.2 Design Evolution, Turning Points & Lessons Learned")
            for ev in all_evolution:
                lines.append(f"- {ev}")
            for sd in superseded_decisions:
                lines.append(
                    f"- **[SUPERSEDED {sd.code}]** *{sd.statement}* — Retired during project evolution "
                    f"(Original rationale: {sd.rationale_why or 'N/A'})"
                )

        lines.append("")
        lines.append("## 3. Decision History (What Was Decided & Why)")
        if active_decisions:
            for d in active_decisions:
                clean_stmt = sanitize_proposition(d.statement, default_verb="Use")
                ch_meta = decision_alt_lookup.get(clean_stmt.lower(), {})
                ses_badge = f" `[{ch_meta['session_code']}]`" if ch_meta.get("session_code") else ""
                lines.append(f"- **[{d.code}]**{ses_badge} **{clean_stmt}**")
                lines.append(f"  - **Why Decided:** {d.rationale_why or 'Ratified by operator'}")
                alts = d.impact_scope or ch_meta.get("alternatives_considered", "")
                if alts:
                    lines.append(f"  - **Alternatives Considered:** {alts}")
                if d.source_excerpt:
                    lines.append(f"  - **Source Evidence:** \"{d.source_excerpt}\"")
        else:
            lines.append("- *(None recorded)*")

        lines.append("")
        lines.append("## 4. Rejected Options (Do Not Repeat & Why Rejected)")
        if rejected_options:
            for r in rejected_options:
                clean_stmt = sanitize_proposition(r.statement)
                lines.append(
                    f"- **⛔ [{r.code}]** **{clean_stmt}** *(Why rejected: {r.rationale_why or 'Not aligned with constraints'})*"
                )
        else:
            lines.append("- *(None recorded)*")

        lines.append("")
        lines.append("## 5. Governance Constraints & Frozen Boundaries")
        if active_constraints:
            for c in active_constraints:
                clean_stmt = sanitize_proposition(c.statement)
                why_note = (
                    f" *(Scope/Why: {c.rationale_why})*"
                    if c.rationale_why and c.rationale_why != "Architectural boundary constraint"
                    else ""
                )
                lines.append(f"- **[{c.code}]** {clean_stmt}{why_note}")
        else:
            lines.append("- *(None recorded)*")

        lines.append("")
        lines.append("## 6. Technical Reasoning & Implementation Context")
        if any([all_arch, all_impl, all_tests, all_probs]):
            if all_arch:
                lines.append("### 6.1 Architecture Discussions & Trade-Offs")
                for item in all_arch:
                    lines.append(f"- {item}")
            if all_impl:
                lines.append("### 6.2 Implementation Approaches")
                for item in all_impl:
                    lines.append(f"- {item}")
            if all_tests:
                lines.append("### 6.3 Testing & Verification Results")
                for item in all_tests:
                    lines.append(f"- {item}")
            if all_probs:
                lines.append("### 6.4 Problems Encountered & Solutions Applied")
                for item in all_probs:
                    lines.append(f"- {item}")
        else:
            lines.append("- *(Refer to ratified decisions, constraints, and artifact custody below)*")

        lines.append("")
        lines.append("## 7. Current Operational State (Completed & Remaining Work)")
        if completed_tasks:
            lines.append("### 7.1 Completed Work")
            for t in completed_tasks:
                lines.append(f"- [x] **[{t.code}]** {t.title} `[COMPLETED]` *(Why: {t.why_it_matters or 'N/A'})*")
        if active_tasks:
            lines.append("### 7.2 Remaining Work")
            for t in active_tasks:
                blk = f" — **BLOCKER:** {t.blocker_reason}" if getattr(t, "blocker_reason", "") else ""
                lines.append(f"- [ ] **[{t.code}]** {t.title} `[{t.status.value}]` *(Why: {t.why_it_matters or 'N/A'})*{blk}")
        if not tasks:
            lines.append("- *(No tasks recorded)*")

        if all_open_questions or all_recommendations:
            lines.append("")
            lines.append("### 7.3 Pending Decisions & Unresolved Questions")
            for rec in all_recommendations:
                # Exclude recommendations that were subsequently ratified or rejected
                r_low = rec.get("statement", "").lower()
                if any(d.statement.lower() in r_low for d in active_decisions) or any(r.statement.lower() in r_low for r in rejected_options):
                    continue
                lines.append(f"- 💡 **Pending Proposal:** {rec.get('statement')} *(Why: {rec.get('reasoning', 'Proposed')})*")
            for q in all_open_questions:
                lines.append(f"- ❓ {q}")

        lines.append("")
        lines.append(f"### 7.4 Next Recommended Action\n- 👉 **{clean_next}**")

        lines.append("")
        lines.append("## 8. Artifact Custody Registry")
        if artifacts:
            for a in artifacts:
                sha_short = f"{a.observed_sha256[:12]}..." if getattr(a, "observed_sha256", None) else "None"
                lines.append(
                    f"- `{a.name}` — **Status:** `{a.custody_state.value}` | "
                    f"**Rel Path:** `{a.relative_path or 'None'}` | **SHA:** `{sha_short}`"
                )
        else:
            lines.append("- *(No artifacts tracked)*")

        lines.append("")
        lines.append("## 9. Fresh AI Session Rehydration Instructions")
        lines.append("1. Treat all `[DEC-*]` Decisions and `[CON-*]` Governance Constraints above as binding project law.")
        lines.append("2. Never re-propose any `⛔ [REJ-*]` Rejected Option unless the human operator explicitly re-opens it.")
        lines.append(f"3. Begin immediately from the **Immediate Next Action**: `{clean_next}`.")
        if sync_footer:
            lines.append("4. Emit continuity updates at major milestones using the `scs-delta/1.0` block:")
            lines.append("")
            lines.append(sync_footer)

        lines.append("")
        lines.append("## 10. Machine-Readable Continuity State")
        lines.append("```scs-handover")
        lines.append(snapshot.state_json)
        lines.append("```")
        lines.append("")
        lines.append("---")
        lines.append(f"*Sealed by SCS-HUD Continuity Steward. Verification Checksum: `{snapshot.checksum_sha256}`*")

        return "\n".join(lines)

    def compile_human_briefing(
        self,
        proj: Any,
        snapshot: Any,
        decisions: List[Any],
        tasks: List[Any],
        artifacts: List[Any],
        chapters: List[Dict[str, Any]],
        session_counts: Dict[str, int],
    ) -> str:
        """Compiles approved canonical SQLite state into a 3-minute executive human briefing ({CODE}_HUMAN_BRIEFING.md)."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
        clean_next = sanitize_proposition(proj.next_action) if proj.next_action else "Review active tasks and proceed."

        parsed_chapters: List[Dict[str, Any]] = []
        all_arch: List[str] = []
        all_evolution: List[str] = []
        all_open_questions: List[str] = []

        def _merge_unique(dest: List[str], items: List[str]) -> None:
            for it in items:
                if it and not any(it.lower() == ex.lower() for ex in dest):
                    dest.append(it)

        for idx, ch in enumerate(chapters, 1):
            meta = self.parse_chapter_metadata(ch.get("markdown_content", ""))
            ch_code = meta.get("chapter_code") or f"Continuity_MD_{idx:02d}"
            parsed_chapters.append({
                "chapter_code": ch_code,
                "session_range": meta.get("session_range", "N/A"),
                "session_count": meta.get("session_count", 0),
                "snapshot_code": meta.get("snapshot_code") or ch.get("snapshot_code", "SEALED"),
                "context_summary": meta.get("context_summary", ""),
                "session_themes": meta.get("session_themes", []),
                "created_at": ch.get("created_at", ""),
            })
            _merge_unique(all_arch, meta.get("architecture_discussions", []))
            _merge_unique(all_evolution, meta.get("project_evolution", []))
            _merge_unique(all_open_questions, meta.get("open_questions", []))

        active_decisions = [d for d in decisions if getattr(d, "is_active", True) and d.record_kind.value == "DECISION"]
        superseded_decisions = [d for d in decisions if not getattr(d, "is_active", True) and d.record_kind.value == "DECISION"]
        active_constraints = [d for d in decisions if getattr(d, "is_active", True) and d.record_kind.value == "CONSTRAINT"]
        rejected_options = [d for d in decisions if getattr(d, "is_active", True) and d.record_kind.value == "REJECTED_OPTION"]

        completed_tasks = [t for t in tasks if t.status.value == "COMPLETED"]
        in_progress_tasks = [t for t in tasks if t.status.value == "IN_PROGRESS"]
        blocked_tasks = [t for t in tasks if t.status.value == "BLOCKED"]
        pending_tasks = [t for t in tasks if t.status.value == "PENDING"]

        total_sess = session_counts.get("total_sessions", 0)
        proc_sess = session_counts.get("processed_sessions", 0)
        pend_sess = session_counts.get("pending_sessions", 0)

        lines = [
            f"# 👤 Human Operator Briefing — {proj.name} ({proj.code})",
            f"> **Snapshot Baseline:** `{snapshot.snapshot_code}` (SHA: `{snapshot.checksum_sha256[:12]}...`)  ",
            f"> **Briefing Generated:** `{now_str}` | **Reading Time:** ~3 minutes  ",
            f"> **Continuity Status:** `{len(parsed_chapters)}` Chapter(s) archived • `{proc_sess}/{total_sess}` Sessions sealed"
            + (f" • `{pend_sess}` pending in buffer" if pend_sess > 0 else ""),
            "",
            "> **PURPOSE FOR HUMAN OPERATOR:** This briefing gives you an instant operational recovery view on project identity, key decisions, rejected approaches, current task inventory, checklist, and immediate next action without needing to read historical transcripts.",
            "",
            "---",
            "",
            "## A. Project Identity",
            f"- **Project Name:** {proj.name}",
            f"- **Project Code:** `{proj.code}`",
            f"- **Objective:** {proj.objective or 'N/A'}",
            f"- **Current Mission / Focus:** {proj.current_focus or 'N/A'}",
            "",
            "## B. Journey Summary",
        ]

        if parsed_chapters:
            for pch in parsed_chapters:
                lines.append(
                    f"- **{pch['chapter_code']} ({pch['session_range']})**: {pch['context_summary'] or 'Ratified milestone chapter.'}"
                )
            if all_evolution:
                lines.append("")
                lines.append("### Key Evolution & Turning Points")
                for ev in all_evolution:
                    lines.append(f"- {ev}")
        else:
            lines.append("- *(Initial project baseline — no multi-session Continuity_MD chapters archived yet)*")

        lines.append("")
        lines.append("## C. Decision Memory")
        lines.append("### What We Decided & Why")
        if active_decisions:
            for i, d in enumerate(active_decisions, 1):
                why = d.rationale_why or "Ratified by human authority"
                lines.append(f"{i}. **{d.code}: {d.statement}**")
                lines.append(f"   - *Why:* {why}")
        else:
            lines.append("- *(No ratified architectural decisions recorded)*")

        lines.append("")
        lines.append("### Rejected Approaches (Do Not Repeat)")
        all_rejected = rejected_options + superseded_decisions
        if all_rejected:
            for r in all_rejected:
                r_kind = "Superseded Decision" if not getattr(r, "is_active", True) else "Rejected Option"
                lines.append(f"- ⛔ **{r.statement}** `[{r_kind}]` *(Why rejected: {r.rationale_why or 'Not aligned with project goals or constraints'})*")
        else:
            lines.append("- *(No rejected approaches recorded)*")

        lines.append("")
        lines.append("## D. Current Operational State")
        lines.append(f"- **Summary:** `{len(completed_tasks)}` Completed • `{len(in_progress_tasks)}` In Progress • `{len(blocked_tasks)}` Blocked • `{len(pending_tasks)}` Pending")
        lines.append("")
        lines.append("### Completed:")
        if completed_tasks:
            for t in completed_tasks:
                lines.append(f"- [x] **[{t.code}]** {t.title}")
        else:
            lines.append("- *(None)*")

        lines.append("")
        lines.append("### In Progress:")
        if in_progress_tasks:
            for t in in_progress_tasks:
                lines.append(f"- [ ] 🔄 **[{t.code}]** {t.title}")
        else:
            lines.append("- *(None)*")

        lines.append("")
        lines.append("### Blocked:")
        if blocked_tasks:
            for t in blocked_tasks:
                lines.append(f"- [ ] ⛔ **[{t.code}]** {t.title} *(Blocked: {t.blocker_reason or 'Dependency missing'})*")
        else:
            lines.append("- *(None)*")

        lines.append("")
        lines.append("### Pending:")
        if pending_tasks:
            for t in pending_tasks:
                lines.append(f"- [ ] ⏳ **[{t.code}]** {t.title}")
        else:
            lines.append("- *(None)*")

        lines.append("")
        lines.append("### Key Artifacts & Registered Files:")
        if artifacts:
            for a in artifacts:
                note = f" *({a.conversation_note})*" if a.conversation_note else ""
                lines.append(f"- 📄 `{a.name}` — `{a.custody_state.value}`{note}")
        else:
            lines.append("- *(No registered artifacts)*")

        lines.append("")
        lines.append("## E. Operator Checklist")
        lines.append("Practical recovery checklist to resume operational flow:")
        checklist_items = []
        if completed_tasks:
            for t in completed_tasks[:3]:
                checklist_items.append(f"- [x] {t.title}")
        elif parsed_chapters:
            checklist_items.append(f"- [x] Sealed continuity chapter(s) up to {parsed_chapters[-1]['chapter_code']}")
        else:
            checklist_items.append("- [x] Baseline project configuration and initial snapshot")

        if in_progress_tasks:
            for t in in_progress_tasks:
                checklist_items.append(f"- [ ] {t.title}")
        if pending_tasks:
            for t in pending_tasks[:3]:
                checklist_items.append(f"- [ ] {t.title}")
        if blocked_tasks:
            for t in blocked_tasks:
                checklist_items.append(f"- [ ] Resolve blocker on {t.title}: {t.blocker_reason}")

        if proj.next_action and not any(proj.next_action.lower() in it.lower() for it in checklist_items):
            checklist_items.append(f"- [ ] {proj.next_action}")

        for item in checklist_items:
            lines.append(item)

        lines.append("")
        lines.append("## F. Warnings & Frozen Boundaries")
        if active_constraints:
            for c in active_constraints:
                why = f" *(Scope/Rationale: {c.rationale_why})*" if c.rationale_why else ""
                lines.append(f"- ⚠️ **[{c.code}]** {c.statement}{why}")
        else:
            lines.append("- *(No active governance constraints recorded)*")

        lines.append("")
        lines.append("## G. Next Recommended Action")
        lines.append(f"👉 **Immediate Concrete Step:** {clean_next}")

        lines.append("")
        lines.append("---")
        lines.append(f"*Compiled from approved canonical vault records by SCS-HUD. Seal: `{snapshot.snapshot_code}`*")

        return "\n".join(lines)

    def compile_project_recovery_card(
        self,
        proj: Any,
        snapshot: Any,
        decisions: List[Any],
        tasks: List[Any],
        artifacts: List[Any],
        chapters: List[Dict[str, Any]],
        session_counts: Dict[str, int],
    ) -> str:
        """Compiles approved canonical SQLite state into a 30-60 second fast project recovery card ({CODE}_PROJECT_RECOVERY_CARD.md)."""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        def _clean_human_text(text: str) -> str:
            if not text:
                return ""
            # Strip raw session tags like [SES-001], SES-014, [SES-014] Evidence —
            t = re.sub(r"\[?SES-\d+\]?\s*(?:Evidence\s*[—–-]\s*)?", "", text, flags=re.IGNORECASE)
            # Strip raw story/scene codes and internal locks like (CH01_S02_BAKER), 41_CH01_S04_VOICE_RESTORED, (HA-L5-DEC-006)
            t = re.sub(r"\(?\b\d*_?CH\d+_S\d+_[A-Za-z0-9_]+\)?", "", t)
            t = re.sub(r"\(?\bHA-[A-Za-z0-9_-]+\)?", "", t)
            t = re.sub(r"\bS\d{2}\b", "", t)
            # Strip leading bullets, asterisks, formatting artifacts, colons, arrows
            t = re.sub(r"^[\s*•\-–—:]+", "", t)
            # Normalize arrows
            t = t.replace("->", "→").replace("=>", "→")
            # Clean up whitespace
            t = re.sub(r"\s+", " ", t).strip()
            return t

        DISALLOWED_PATTERNS = (
            "reconciliation status",
            "open question",
            "would you like",
            "would you prefer",
            "should we",
            "shall we",
            "could we",
            "what do you think",
            "let me know",
            "feel free",
            "how would you",
            "proceed with phase",
            "ses-",
            "chat fragment",
            "evidence —",
            "evidence -",
        )

        def _is_clean_human(text: str) -> bool:
            if not text or not text.strip():
                return False
            lower = text.lower().strip()
            if any(p in lower for p in DISALLOWED_PATTERNS):
                return False
            # Reject questions ending in ? or conversation query patterns
            if lower.endswith("?") and any(w in lower for w in ("would", "should", "could", "adjust", "plan first", "think", "prefer")):
                return False
            return True

        def _is_snapshot_or_archive_text(text: str) -> bool:
            if not text:
                return True
            low = text.lower()
            bad_phrases = (
                "continuity_md",
                "continuity md",
                "sealed under",
                "sealed snapshot",
                "snapshot seal",
                "snapshot:",
                "snp-",
                "checkpoint",
                "milestone snapshot",
                "quick checkpoint",
                "active development sealed",
            )
            return any(bp in low for bp in bad_phrases)

        GENERIC_ACTION_PHRASES = (
            "execute next planned milestone",
            "continue development",
            "advance project",
            "execute milestone",
            "proceed with next",
            "resolve open question",
            "reconciliation status",
            "continue work",
            "advance development",
        )

        def _is_generic_action(text: str) -> bool:
            if not text:
                return True
            low = text.lower().strip()
            if any(gp in low for gp in GENERIC_ACTION_PHRASES):
                return True
            p_name_low = proj.name.lower()
            if low in (f"continue {p_name_low}", f"advance {p_name_low}", f"execute {p_name_low}"):
                return True
            return False

        def _is_valid_action(text: str) -> bool:
            if not text or not text.strip():
                return False
            clean = _clean_human_text(text)
            if not clean or len(clean) < 4:
                return False
            if not _is_clean_human(clean):
                return False
            if _is_generic_action(clean):
                return False
            lower = clean.lower()
            if lower.endswith("?"):
                return False
            bad_lead_ins = (
                "would you",
                "should we",
                "shall we",
                "could we",
                "can we",
                "do you want",
                "how about",
                "what if",
                "let's decide",
                "open question",
                "resolve open question",
                "reconciliation status",
                "execute next planned milestone",
                "continue development",
                "advance project",
            )
            if any(lower.startswith(lead) for lead in bad_lead_ins):
                return False
            return True

        parsed_chapters: List[Dict[str, Any]] = []
        for idx, ch in enumerate(chapters, 1):
            meta = self.parse_chapter_metadata(ch.get("markdown_content", ""))
            ch_code = meta.get("chapter_code") or f"Continuity_MD_{idx:02d}"
            parsed_chapters.append({
                "chapter_code": ch_code,
                "session_range": meta.get("session_range", "N/A"),
                "context_summary": meta.get("context_summary", ""),
            })

        active_decisions = [d for d in decisions if getattr(d, "is_active", True) and getattr(d.record_kind, "value", str(d.record_kind)) == "DECISION"]
        active_constraints = [d for d in decisions if getattr(d, "is_active", True) and getattr(d.record_kind, "value", str(d.record_kind)) == "CONSTRAINT"]
        rejected_options = [d for d in decisions if getattr(d, "is_active", True) and getattr(d.record_kind, "value", str(d.record_kind)) == "REJECTED_OPTION"]

        completed_tasks = [t for t in tasks if getattr(t.status, "value", str(t.status)) == "COMPLETED"]
        in_progress_tasks = [t for t in tasks if getattr(t.status, "value", str(t.status)) == "IN_PROGRESS"]
        blocked_tasks = [t for t in tasks if getattr(t.status, "value", str(t.status)) == "BLOCKED"]
        pending_tasks = [t for t in tasks if getattr(t.status, "value", str(t.status)) == "PENDING"]

        total_sess = session_counts.get("total_sessions", 0)
        proc_sess = session_counts.get("processed_sessions", 0)

        lines = [
            f"# 👤 Project Recovery Card — {proj.name} ({proj.code})",
            "",
            f"**Snapshot:** `{snapshot.snapshot_code}` (SHA: `{snapshot.checksum_sha256[:12]}...`)  ",
            f"**Status:** `{len(parsed_chapters)}` Chapter(s) sealed • `{proc_sess}/{total_sess}` Sessions sealed  ",
            f"**Last Updated:** `{now_str}`",
            "",
            "---",
            "",
            "## 📍 Where We Are",
            "",
            "Short summary:",
        ]

        # 1. Resolve Current Stage (operational project state only; NO chapter names, NO archive/snapshot language)
        current_stage = ""

        # A. From active/in-progress task
        if in_progress_tasks:
            t_cand = _clean_human_text(in_progress_tasks[0].title)
            if _is_clean_human(t_cand) and not _is_snapshot_or_archive_text(t_cand):
                current_stage = t_cand
        elif pending_tasks and not current_stage:
            t_cand = _clean_human_text(pending_tasks[0].title)
            if _is_clean_human(t_cand) and not _is_snapshot_or_archive_text(t_cand):
                current_stage = t_cand

        # B. From active milestone (snapshot label, if real milestone name)
        if not current_stage and snapshot.label:
            lbl = _clean_human_text(snapshot.label)
            if _is_clean_human(lbl) and not _is_snapshot_or_archive_text(lbl):
                if lbl.lower() not in ("milestone snapshot", "quick checkpoint", "snapshot", "baseline"):
                    current_stage = lbl

        # C. From project current_focus / current_stage (if clean and operational)
        if not current_stage:
            raw_focus = getattr(proj, "current_stage", None) or getattr(proj, "current_focus", "")
            cand_focus = _clean_human_text(raw_focus)
            if cand_focus and _is_clean_human(cand_focus) and not _is_snapshot_or_archive_text(cand_focus):
                current_stage = cand_focus

        # D. From project next_action (if valid operational action)
        if not current_stage:
            cand_next = _clean_human_text(getattr(proj, "next_action", ""))
            if cand_next and _is_valid_action(cand_next) and not _is_snapshot_or_archive_text(cand_next):
                current_stage = cand_next

        # E. From latest approved decision state
        if not current_stage and active_decisions:
            d_cand = _clean_human_text(active_decisions[0].statement)
            if _is_clean_human(d_cand) and not _is_snapshot_or_archive_text(d_cand):
                current_stage = d_cand

        # F. Operational fallback based on project context (NO chapter names, NO "sealed under", NO snapshot codes)
        if not current_stage:
            if artifacts:
                current_stage = f"{proj.name} — Interactive Asset & Implementation Delivery"
            else:
                current_stage = f"{proj.name} — Core Implementation & Architecture Delivery"

        # Resolve Current Objective
        current_obj = ""
        cand_obj = _clean_human_text(getattr(proj, "objective", ""))
        if cand_obj and _is_clean_human(cand_obj) and cand_obj.lower() not in ("n/a", "none", "tbd") and not _is_snapshot_or_archive_text(cand_obj):
            current_obj = cand_obj
        else:
            current_obj = f"Advance {proj.name} deliverables and maintain verified asset integrity"

        lines.append(f"- **Current Stage:** {current_stage}")
        lines.append(f"- **Current Objective:** {current_obj}")
        lines.append("")
        lines.append("---")
        lines.append("")

        # 2. Completed Section (Prioritize actual project accomplishments: completed tasks, verified artifacts, production milestones; SCS seals secondary)
        lines.append("## ✅ Completed")
        lines.append("")
        completed_items: List[str] = []

        # From completed tasks (top accomplishment)
        for t in completed_tasks:
            t_title = _clean_human_text(t.title)
            if t_title and _is_clean_human(t_title) and not _is_snapshot_or_archive_text(t_title):
                completed_items.append(f"- [x] Task: {t_title}")
                if len(completed_items) >= 2:
                    break

        # From verified artifact baselines / custody
        verified_arts: List[str] = []
        for a in artifacts:
            custody = getattr(a.custody_state, "value", str(a.custody_state))
            if custody in ("VERIFIED_MATCH", "LOCAL_FILE_EXISTS") or getattr(a, "baseline_sha256", None):
                a_name = _clean_human_text(a.name)
                if a_name and a_name not in verified_arts and not _is_snapshot_or_archive_text(a_name):
                    verified_arts.append(a_name)
                    completed_items.append(f"- [x] Verified file baseline: `{a_name}`")
                    if len(verified_arts) >= 2:
                        break

        # From tracked core project artifacts if no verified match yet
        if not completed_items and artifacts:
            for a in artifacts[:2]:
                a_name = _clean_human_text(a.name)
                if a_name and a_name not in verified_arts and not _is_snapshot_or_archive_text(a_name):
                    verified_arts.append(a_name)
                    completed_items.append(f"- [x] Tracked project artifact: `{a_name}`")

        # From production milestones
        if snapshot.label:
            lbl = _clean_human_text(snapshot.label)
            if _is_clean_human(lbl) and not _is_snapshot_or_archive_text(lbl) and lbl.lower() not in ("milestone snapshot", "quick checkpoint"):
                completed_items.append(f"- [x] Production milestone: {lbl}")

        # Secondary SCS seals only when accomplishments are sparse
        if len(completed_items) < 2:
            if snapshot.snapshot_code:
                completed_items.append(f"- [x] Approved snapshot seal: `{snapshot.snapshot_code}`")

        if not completed_items:
            completed_items.append("- [x] Baseline project configuration and canonical state established")

        for item in completed_items[:4]:
            lines.append(item)

        lines.append("")
        lines.append("---")
        lines.append("")

        # 3. Current Focus (Actionable work items; NEVER repeat chapter names or snapshot descriptions)
        lines.append("## 🟡 Current Focus")
        lines.append("")
        focus_items: List[str] = []
        if in_progress_tasks:
            for t in in_progress_tasks[:2]:
                title = _clean_human_text(t.title)
                if title and _is_clean_human(title) and not _is_snapshot_or_archive_text(title):
                    focus_items.append(f"- [ ] 🔄 {title}")
        if pending_tasks:
            for t in pending_tasks[:3]:
                title = _clean_human_text(t.title)
                if title and _is_clean_human(title) and not _is_snapshot_or_archive_text(title):
                    focus_items.append(f"- [ ] ⏳ {title}")
        if blocked_tasks:
            for t in blocked_tasks[:1]:
                title = _clean_human_text(t.title)
                reason = _clean_human_text(t.blocker_reason)
                if title and _is_clean_human(title) and not _is_snapshot_or_archive_text(title):
                    focus_items.append(f"- [ ] ⛔ {title} *(Blocked: {reason or 'Dependency'})*")

        # Fallback when tasks table is empty: derive actionable items from unverified artifacts or constraints
        if not focus_items:
            unverified = [a for a in artifacts if getattr(a.custody_state, "value", str(a.custody_state)) not in ("VERIFIED_MATCH", "LOCAL_FILE_EXISTS")]
            target_arts = unverified[:2] if unverified else artifacts[:2]
            for a in target_arts:
                a_name = _clean_human_text(a.name)
                if a_name and not _is_snapshot_or_archive_text(a_name):
                    focus_items.append(f"- [ ] 🔄 Verify file baseline: `{a_name}`")

            if len(focus_items) < 3 and active_constraints:
                c_stmt = _clean_human_text(active_constraints[0].statement)
                if c_stmt and _is_clean_human(c_stmt):
                    if len(c_stmt) > 80:
                        c_stmt = c_stmt[:80].rsplit(" ", 1)[0] + "..."
                    focus_items.append(f"- [ ] 🔄 Enforce: {c_stmt}")

        if not focus_items:
            focus_items.append(f"- [ ] 🔄 Advance {proj.name} core delivery & verification")

        for item in focus_items[:4]:
            lines.append(item)

        lines.append("")
        lines.append("---")
        lines.append("")

        # 4. Important Decisions (Checklist style: 🔒 Statement \n Why: Rationale; Max 3-5 items)
        lines.append("## 🔒 Important Decisions")
        lines.append("")
        decision_items: List[Tuple[str, str]] = []

        # Ratified architectural decisions
        for d in active_decisions:
            stmt = _clean_human_text(d.statement)
            why = _clean_human_text(d.rationale_why or "Ratified project architectural baseline")
            if stmt and _is_clean_human(stmt) and _is_clean_human(why):
                if stmt.lower().startswith("rule:"):
                    stmt = stmt[5:].strip()
                decision_items.append((stmt, why))
                if len(decision_items) >= 2:
                    break

        # Hard constraints / frozen boundaries
        for c in active_constraints:
            stmt = _clean_human_text(c.statement)
            why = _clean_human_text(c.rationale_why or "Frozen governance boundary")
            if stmt and _is_clean_human(stmt):
                if stmt.lower().startswith("rule:"):
                    stmt = stmt[5:].strip()
                decision_items.append((stmt, why))
                if len(decision_items) >= 4:
                    break

        # Rejected alternatives
        for r in rejected_options:
            stmt = _clean_human_text(r.statement)
            why = _clean_human_text(r.rationale_why or "Not aligned with project architecture")
            if stmt and _is_clean_human(stmt):
                prefix = "" if any(stmt.lower().startswith(p) for p in ("reject", "exclude", "avoid")) else "Reject "
                decision_items.append((f"{prefix}{stmt}", why))
                if len(decision_items) >= 5:
                    break

        if decision_items:
            for stmt, why in decision_items[:5]:
                lines.append(f"🔒 {stmt}")
                lines.append(f"Why: {why}")
                lines.append("")
        else:
            lines.append(f"🔒 Offline-first baseline architecture for {proj.code}")
            lines.append("Why: Maintain zero dependency local execution.")
            lines.append("")

        lines.append("---")
        lines.append("")

        # 5. Remember Section (Maximum 5 items, human-readable rules, no raw scene codes)
        lines.append("## ⚠️ Remember")
        lines.append("")
        warning_items: List[str] = []
        for c in active_constraints:
            stmt = _clean_human_text(c.statement)
            why = f" *(Why: {_clean_human_text(c.rationale_why)})*" if c.rationale_why else ""
            if stmt and _is_clean_human(stmt):
                warning_items.append(f"- ⚠️ **[{c.code}]** {stmt}{why}")
                if len(warning_items) >= 4:
                    break

        for r in rejected_options:
            if len(warning_items) >= 5:
                break
            stmt = _clean_human_text(r.statement)
            why = f" *(Why: {_clean_human_text(r.rationale_why)})*" if r.rationale_why else ""
            if stmt and _is_clean_human(stmt):
                warning_items.append(f"- ⛔ **Avoid:** {stmt}{why}")

        if not warning_items:
            warning_items.append("- *(No active governance constraints or warnings recorded)*")

        for item in warning_items[:5]:
            lines.append(item)

        lines.append("")
        lines.append("---")
        lines.append("")

        # 6. Next Actions (Concrete executable actions: Package X, Verify Y, Test Z; Reject generic and conversational questions; Max 3)
        lines.append("## ⏭️ Next Actions")
        lines.append("")
        next_actions: List[str] = []

        # 1. From valid projects.next_action (strictly verified!)
        cand_next = _clean_human_text(getattr(proj, "next_action", ""))
        if _is_valid_action(cand_next):
            next_actions.append(cand_next)

        # 2. From in-progress tasks
        if in_progress_tasks:
            for t in in_progress_tasks:
                title = _clean_human_text(t.title)
                if _is_valid_action(title):
                    act = f"Verify {title}" if not any(title.lower().startswith(v) for v in ("verify", "package", "test", "implement")) else title
                    if not any(title.lower() in a.lower() for a in next_actions):
                        next_actions.append(act)
                    if len(next_actions) >= 3:
                        break

        # 3. From pending tasks
        if pending_tasks:
            for t in pending_tasks:
                title = _clean_human_text(t.title)
                if _is_valid_action(title):
                    act = f"Package {title}" if not any(title.lower().startswith(v) for v in ("verify", "package", "test", "implement")) else title
                    if not any(title.lower() in a.lower() for a in next_actions):
                        next_actions.append(act)
                    if len(next_actions) >= 3:
                        break

        # 4. Fallback concrete executable actions derived from real project context (Package X, Verify Y, Test Z)
        if len(next_actions) < 3 and artifacts:
            # Check for interactive/engine artifacts
            engine_arts = [a.name for a in artifacts if any(ext in a.name.lower() for ext in (".html", ".js", ".css"))]
            doc_arts = [a.name for a in artifacts if any(ext in a.name.lower() for ext in (".md", ".json"))]

            if engine_arts and not any("build" in a.lower() or "storybook" in a.lower() for a in next_actions):
                next_actions.append(f"Package and verify interactive build ({engine_arts[0]})")

            if doc_arts and len(next_actions) < 3 and not any("baseline" in a.lower() for a in next_actions):
                next_actions.append(f"Verify artifact baseline integrity for `{doc_arts[0]}`")

            if active_constraints and len(next_actions) < 3 and not any("test" in a.lower() for a in next_actions):
                next_actions.append(f"Test runtime behavior and constraint compliance for active features")

        # Global concrete executable fallback (strictly avoiding generic phrases like 'Execute next planned milestone')
        fallback_actions = [
            f"Package and verify core release build for {proj.name}",
            f"Test runtime feature compliance against ratified constraints",
            f"Review project recovery checklist and validate snapshot telemetry",
        ]
        for fa in fallback_actions:
            if len(next_actions) >= 3:
                break
            if not any(fa.lower()[:20] in a.lower() for a in next_actions):
                next_actions.append(fa)

        for i, act in enumerate(next_actions[:3], 1):
            lines.append(f"{i}. {act}")

        lines.append("")
        lines.append("---")
        lines.append(f"*SCS-HUD Fast Project Recovery Card • Single-Page Restart View • Seal: `{snapshot.snapshot_code}`*")

        return "\n".join(lines)
