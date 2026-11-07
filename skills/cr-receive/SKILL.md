---
name: cr-receive
description: Inform users that cr-receive has been renamed to cr-received and show how to install the replacement. Use when a user invokes cr-receive or asks about its new name.
---

# CR Receive has moved

`cr-receive` was renamed to `cr-received`. Install the replacement with:

```bash
npx skills add sentimony/agentic-workflow -s cr-received -a codex claude-code -y
```

When invoked, explain the rename and show this command. The user decides whether to run
it. Use `cr-received` for subsequent review-finding resolution when it is available.
