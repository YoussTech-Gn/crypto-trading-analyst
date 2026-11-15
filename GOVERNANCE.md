# Governance

This project is owner-led and community-driven. Contributions are welcome; repository ownership and administrative access remain with the project owner.

## Roles

- **Project owner — YoussTech-Gn:** sets project direction, manages repository settings and access, and makes final decisions.
- **Contributors:** propose changes through issues and pull requests. Write access is not required to contribute.
- **Maintainers:** contributors explicitly appointed by the owner to help triage issues, review pull requests, maintain documentation and tests, and merge changes only when granted the required GitHub permissions.

Contributing does not automatically grant maintainer status or write access.

## Becoming a maintainer

The owner may invite a contributor to become a maintainer based on sustained constructive contributions, sound technical judgment, helpful reviews, familiarity with the architecture and research methodology, respect for security boundaries, and consistent adherence to the project's evidence-first process.

Before appointment, the owner and candidate should agree on responsibilities and access. Record the appointment in `MAINTAINERS.md` and grant the minimum GitHub permission needed. Access may be changed or withdrawn when responsibilities change.

## Reviews and decisions

- Use GitHub Issues for bugs and proposals, and Pull Requests for code or documentation changes.
- Pull requests should explain the motivation, scope, risks, and verification performed.
- Authors must not approve their own pull requests. A maintainer should review changes they did not author where practical.
- Changes to research assumptions, parameters, fees, data windows, metrics, thresholds, or conclusions must be documented in `docs/DECISIONS.md` before an experiment runs.
- Never change a pre-registered experiment rule after inspecting its results.
- Changes that could weaken paper-only safeguards, expose private data, or introduce exchange trading capability require explicit project-owner review.
- Discuss disagreements respectfully and keep the reasoning in the relevant issue or pull request. The project owner has final decision authority while the project remains owner-led.

## Releases and repository access

The project owner controls repository administration, releases, and maintainer appointments. Maintainers may prepare release notes and recommend releases; publishing authority is delegated only explicitly.

Never share personal accounts, access tokens, or credentials. Never commit secrets, private journal entries, or personal data.

## Changing this policy

Anyone may propose a governance change through an issue or pull request. The project owner approves changes to this policy and the maintainer roster.
