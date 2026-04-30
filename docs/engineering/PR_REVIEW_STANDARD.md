# Pull Request Review Standard

**Version:** 1.0  
**Owner:** Engineering Lead / Team Lead  
**Applies to:** All code changes merged into main branches

---

## Purpose

This document defines how pull requests are created, reviewed, approved, and merged to maintain code quality, reduce bugs, and keep changes understandable.

## Objectives

- Improve code quality
- Catch defects early
- Maintain security and performance standards
- Share knowledge across the team
- Keep changes small and easy to review

## PR Author Responsibilities

The author must:

- keep PRs small and focused
- write a clear PR description
- link the relevant ticket, task, or bug
- ensure the code builds successfully
- run tests before requesting review
- add screenshots or demo notes for UI changes
- highlight risky areas or known limitations
- respond to review comments professionally and promptly

## Reviewer Responsibilities

The reviewer must:

- understand the purpose of the change
- check correctness, readability, maintainability, and risk
- verify tests are appropriate
- flag security, performance, and edge-case concerns
- avoid unnecessary style debates if linting and standards already cover them
- approve only when confident the change is safe to merge

## PR Size Guideline

- Preferred: under 400 lines changed
- Avoid mixing unrelated changes in one PR
- Large PRs must be split unless there is a clear reason not to

## Review Criteria

Reviewers should check the following areas.

### Functionality

- Does the code do what the requirement says?
- Are edge cases handled?
- Could this break existing behavior?

### Code Quality

- Is the code readable?
- Are names clear and meaningful?
- Is the logic easy to follow?
- Is duplication avoided?

### Architecture and Design

- Does the change fit the existing design?
- Is the solution over-engineered or too tightly coupled?
- Are responsibilities separated properly?

### Testing

- Are automated tests included where needed?
- Do existing tests still pass?
- Is manual testing explained if automation is not practical?

### Security

- Are inputs validated?
- Are secrets excluded from code?
- Are authentication, permissions, and data exposure handled correctly?

### Performance

- Could this create slow queries, unnecessary renders, memory issues, or network overhead?

### Documentation

- Are README files, API docs, comments, or release notes updated if needed?

## Approval Rules

- At least **1 reviewer approval** is required for normal changes
- At least **2 approvals** are required for:
  - authentication or security changes
  - payment-related changes
  - production infrastructure changes
  - database schema changes
- The author may not self-approve unless working alone and the team has explicitly allowed it

## Merge Rules

A PR may be merged only when:

- required checks pass
- required approvals are completed
- major comments are resolved
- conflicts are resolved
- the branch is up to date if needed

## Review Turnaround

- Normal PRs: review within 1 business day
- Urgent fixes: review as soon as possible
- If a reviewer is blocked, they should communicate quickly

## Comment Categories

Use these labels in comments to make reviews clearer:

- **Must Fix** - required before merge
- **Should Fix** - strong recommendation
- **Question** - clarification needed
- **Suggestion** - optional improvement
- **Nit** - very minor issue

## Dispute Resolution

If the author and reviewer disagree:

1. discuss in PR comments or a quick call
2. align on coding standards or architecture principles
3. escalate to the engineering lead if needed

## Exceptions

Emergency hotfixes may follow a shortened process, but must be reviewed retrospectively after release.

---

## Lightweight Policy for Small Teams

Use this short version in your handbook if you want something simpler.

### PR Review Policy

1. Every code change must go through a pull request.
2. PRs must be small, focused, and clearly described.
3. Authors must test changes before requesting review.
4. At least one reviewer must approve before merge.
5. High-risk changes require two approvals.
6. Reviewers check correctness, readability, testing, security, and impact.
7. All major comments must be resolved before merge.
8. Emergency fixes may be merged quickly but reviewed afterward.

---

## Suggested Repository Structure

```text
/docs/engineering/PR_REVIEW_STANDARD.md
/.github/pull_request_template.md
```

This keeps the policy in version control and the template active inside GitHub.
