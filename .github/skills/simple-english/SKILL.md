---
name: simple-english
description: "Write or review clear technical English for documentation, tickets, commit messages, runbooks, release notes, and SDLC agent instructions. Use plain-language guidance by default and exact ASD-STE100 checks only when requested."
argument-hint: "Describe the text or document and choose plain or strict STE mode if needed."
user-invocable: true
---

# Simple English for Technical Content

This workspace guide is a project-specific paraphrase inspired by [AminBlg/SimpleEnglish](https://github.com/AminBlg/SimpleEnglish), which is MIT licensed, and by ASD-STE100. It does not reproduce the standard's rules or dictionary.

## Plain Mode

Use this mode by default for technical documentation and SDLC artifacts.

- Put the main result or purpose first. Use familiar words, active voice, and simple verb tenses.
- Keep sentences short and focused. Define specialized terms before readers need them.
- Give a condition before its action. State prerequisites, affected systems, and expected results.
- Use one term for one concept throughout a document. Keep product names, identifiers, code, commands, flags, paths, and quoted errors unchanged.
- Preserve meaning, facts, warnings, and technical behavior. Do not make a claim stronger or weaker while simplifying it.
- Use formatting to show real structure. Prefer clear headings, numbered procedures, and parallel lists over decoration.
- Use American English unless the project or audience requires another variant.

For commit messages and tickets, preserve the repository's existing conventions and required fields. Do not apply prose rules in a way that changes identifiers, templates, or meaning.

## Strict STE Mode

Use strict mode only when the user asks for STE, ASD-STE100, or a compliance check.

- Treat `.github/ASD-STE100_ISSUE9.pdf` as the local authority for exact rules and approved vocabulary.
- When available, search the permitted local text extraction at `.copilot/reference/ASD-STE100_ISSUE9.txt`. Use the PDF as the source if search results are unclear.
- Use the [STE-Code adapted dictionary](https://github.com/NikolaRHristov/STE-Code/blob/Current/ste-code/final/rules/a-dictionary.md) only as a secondary, on-demand reference for software terms. Its dictionary says that it is adapted from ASD-STE100 Issue 9, so it is not the official standard or proof of compliance.
- Check the relevant rule and vocabulary in the source before giving rule numbers or word-choice rulings. Do not cite rules or approved terms from memory.
- If current tools cannot search or read the PDF, say that exact checking is unavailable. Offer an STE-inspired edit, but do not claim compliance.
- Keep the authorized text extraction only in the ignored `.copilot/reference/` directory. Do not stage, commit, publish, or share it. Respect the scope of the permission.
- Do not copy the STE-Code dictionary into workspace files. The linked SimpleEnglish project keeps dictionary lists out of its repository because the standard restricts reproduction.
- State that no tool can guarantee ASD-STE100 compliance when the user asks for compliance.

SimpleEnglish is designed for facts and instructions. Do not force its plain style onto marketing or brand copy when that would undermine the requested purpose; explain the tradeoff and apply it to the technical sections instead.

## Final Review

Before delivery, check that the revision preserves all facts, warnings, commands, and technical details. Make sure each instruction names the required actor, condition, and target when the reader needs them. Report any content you could not verify.