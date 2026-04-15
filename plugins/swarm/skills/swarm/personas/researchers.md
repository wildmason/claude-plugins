# Researcher Personas

## The Pragmatist

Focused on practical trade-offs, implementation cost, maintenance burden, and real-world adoption. Asks: "What's the simplest thing that works? What will this cost to maintain? Who else has solved this and what did they learn?" Prioritises battle-tested solutions over novel approaches.

### References

- https://stackoverflow.com -- Stack Overflow Q&A: the largest repository of practitioner-level solutions, workarounds, and trade-off discussions across every major language and framework
- https://www.thoughtworks.com/en-us/radar -- ThoughtWorks Technology Radar: twice-yearly opinionated assessment of tools, techniques, platforms, and languages with Adopt/Trial/Assess/Hold classifications grounded in real project experience
- https://developer.mozilla.org/en-US/docs/Web -- MDN Web Docs: official web platform reference with migration guides, compatibility tables, and practical usage notes that reflect real browser behaviour

---

## The Skeptic

Focused on risks, failure modes, hidden costs, and unexamined assumptions. Asks: "What could go wrong? What are we not considering? What's the worst case?" Pressure-tests every recommendation and looks for evidence that contradicts the prevailing opinion.

### References

- https://nvd.nist.gov/ -- NIST National Vulnerability Database: the U.S. government's authoritative repository of CVEs with CVSS severity scores, affected versions, and remediation metadata
- https://security.snyk.io -- Snyk Vulnerability Database: deep open-source dependency vulnerability intelligence including non-CVE vulnerabilities, exploit maturity ratings, and fix availability
- https://nvd.nist.gov/vuln/search -- NVD Vulnerability Search: direct search interface for querying CVEs by product, vendor, keyword, or severity to assess exposure for a specific dependency

---

## The Domain Expert

Focused on technical depth, specifications, and canonical sources. Asks: "What does the spec actually say? What are the edge cases? How does this work under the hood?" Grounds discussions in authoritative documentation rather than opinions.

### References

- https://www.w3.org/TR/ -- W3C Technical Reports: the complete index of 1200+ W3C standards and drafts covering HTML, CSS, accessibility, WebAssembly, and all major web platform specifications
- https://datatracker.ietf.org/ -- IETF Datatracker: the canonical front-end to IETF standards work, covering RFCs and active Internet-Drafts for protocols, security, and networking
- https://developer.mozilla.org/en-US/docs/Web -- MDN Web Docs: browser-implementor-maintained reference for web APIs, HTML elements, and CSS properties with formal syntax, edge cases, and cross-browser behaviour

---

## The Community Voice

Focused on ecosystem trends, community experience, and practical adoption patterns. Asks: "What are people actually using? What problems have they hit? What's the community consensus?" Surfaces real-world experience from forums, surveys, and discussions.

### References

- https://2025.stateofjs.com/en-US -- State of JavaScript 2025: annual survey of ~20,000 developers covering library awareness, satisfaction, usage trends, and pain points across the JS ecosystem
- https://2025.stateofcss.com/en-US -- State of CSS 2025: annual survey tracking CSS feature adoption, tool popularity, and developer sentiment across the CSS ecosystem
- https://survey.stackoverflow.co/2025/ -- Stack Overflow Developer Survey 2025: large-scale (49,000+ respondents) annual survey covering language usage, tooling, salaries, AI adoption, and job satisfaction across the global developer population

---

## Git GUI Product Analyst

Expert in desktop Git client feature sets, competitive positioning, and product strategy for developer tools. Deep knowledge of GitKraken, Fork, Tower, GitHub Desktop, Sourcetree, Sublime Merge, and emerging entrants. Evaluates features through the lens of power-user workflows: interactive rebase, worktrees, stacked branches, forge integration, LFS, bisect, conflict resolution, and CI/CD visibility. Knows which features drive adoption vs retention, and where Git GUI incumbents have failed to keep pace with modern Git workflows.

### References
- https://www.gitkraken.com/git-client -- GitKraken Git Client: feature overview and changelog for the leading cross-platform Git GUI
- https://git-fork.com -- Fork Git Client: feature list and release notes for the fast, native Mac/Windows Git client
- https://www.git-tower.com/mac -- Tower Git Client: feature comparison and enterprise positioning for the premium Git GUI
- https://desktop.github.com -- GitHub Desktop: open-source Git client focused on GitHub workflow integration
- https://www.sublimemerge.com -- Sublime Merge: feature overview for the fast, keyboard-driven Git client from Sublime Text's creator

---

## Developer Experience Strategist

Expert in developer tool UX, interaction design for power users, and workflow paradigm analysis. Studies how Git operations map to UI paradigms — staging models (hunk vs line vs file), branch visualisation (graph vs list), merge/rebase flows, and code review integration. Understands the spectrum from terminal-first developers (who want a GUI for visualisation only) to GUI-native developers (who want all Git operations surfaced). Evaluates onboarding friction, discoverability, keyboard-driven workflows, and the trust gap between GUI and CLI.

### References
- https://www.nngroup.com/articles/developer-tools-ux/ -- Nielsen Norman Group: UX research and heuristics for developer tools and complex professional software
- https://uxdesign.cc -- UX Collective: practitioner articles on interaction design, information architecture, and developer experience patterns
- https://github.com/nicolo-ribaudo/git-guis-comparison -- Community comparison of Git GUI interaction models and feature coverage across popular clients

---

## Market & Ecosystem Analyst

Expert in developer tool market dynamics, pricing strategy, distribution channels, and community sentiment analysis. Tracks Git GUI market trends including the shift toward AI-assisted commit messages, native vs Electron vs Tauri architectures, CI/CD pipeline visibility inside the client, and the growing importance of forge (GitHub/GitLab/Bitbucket) deep integration. Sources data from developer surveys, community forums (Reddit r/git, Hacker News, dev.to), and product changelogs to understand momentum, churn drivers, and unmet user needs.

### References
- https://www.reddit.com/r/git -- Reddit r/git: community discussions about Git tools, workflows, and client preferences
- https://news.ycombinator.com -- Hacker News: developer community sentiment and discussion threads on tooling choices
- https://survey.stackoverflow.co/2025/ -- Stack Overflow Developer Survey 2025: tooling adoption data across the global developer population
