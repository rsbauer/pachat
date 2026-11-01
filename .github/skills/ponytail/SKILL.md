---
name: ponytail
description: "A lean senior-engineer workflow for coding tasks: writing, fixing, refactoring, reviewing code, and choosing dependencies. Use on coding work or when asked for Ponytail, a simpler solution, YAGNI, or less over-engineering."
argument-hint: "[lite|full|ultra|off]"
user-invocable: true
---

# Ponytail

An adaptation of the workflow in [DietrichGebert/ponytail](https://github.com/DietrichGebert/ponytail), used under its MIT license. Be economical with code, never with understanding or care.

## Before Changing Code

Read the request and the code it touches. Identify the callers, tests, fixtures, configuration, and exports the change may affect. Consider user impact, especially data that could be lost or exposed. Keep scope to what the task requires.

For a bug fix, find the relevant callers before editing and fix the root cause at the owning implementation when possible.

## Choose the Smallest Complete Solution

Consider these options in order, and stop at the first one that fully solves the task:

1. Is this needed? Do not add unrequested features, options, or future flexibility. For a broad request, start with the smallest version that does the core job.
2. Is there already suitable code or a project convention? Reuse it in the way the surrounding code does.
3. Does the standard library or platform provide it? Prefer an existing project component when it is the established choice.
4. Is a suitable dependency already installed? Do not add a dependency for a small amount of straightforward code.
5. Can a clear, direct expression solve it?
6. Otherwise, write the minimum code that works.

Complete every part the change requires, including affected callers, tests, and fixtures. Avoid unrequested abstractions, wrappers, conversions, configuration, boilerplate, and speculative layers. Keep the project's structure and conventions. Prefer deletion over addition when it fully solves the task. Correct edge-case behavior takes priority over a shorter diff.

Preserve existing validation and error handling. Never remove trust-boundary validation, data-loss protection, security, accessibility, hardware calibration, or any behavior the user requested. Add a small focused test or assert-based check for new non-trivial logic, including branches, loops, parsing, money, or security. Trivial changes do not need a test.

If a deliberate shortcut has a known limitation, document it in one concise code comment using this form: `shortcut: <the limit>, <when to upgrade>`.

## Levels

- `lite`: Build what was requested. Mention a smaller viable option in one line when there is a meaningful choice.
- `full`: Use the workflow above. This is the default.
- `ultra`: Also challenge parts of the request that appear to lack a need before implementing them.
- `off`: Stop applying this workflow until it is requested again.

The user can choose a level with `/ponytail lite`, `/ponytail full`, `/ponytail ultra`, or `/ponytail off`, and can return to normal mode by saying “stop ponytail” or “normal mode.”

## Reply

Keep the reply concise. End with one or two lines stating what was skipped or not checked and any risk the user should know. If nothing was skipped and no material risk remains, say so plainly.