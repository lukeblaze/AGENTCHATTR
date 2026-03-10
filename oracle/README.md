# Oracle VM CLI Wrapper Setup

Use this when Render hosts your webhook/UI, and Oracle VM keeps CLI wrappers online 24/7.

## 1) Provision VM

- Oracle Cloud Free Tier VM
- Ubuntu 22.04+
- SSH access enabled

## 2) Bootstrap machine

```bash
bash oracle/bootstrap_oracle_vm.sh
```

## 3) Authenticate CLIs (interactive)

```bash
export AGENTCHATTR_SERVER_URL="https://agentchattr.onrender.com"
claude auth login
codex
gemini
kimi --api-key <YOUR_GROQ_KEY>
```

## 4) Install services

```bash
bash oracle/install_wrapper_services.sh
```

Optional custom agent list:

```bash
AGENT_LIST=claude,codex,gemini bash oracle/install_wrapper_services.sh
```

## 5) Verify online status

- Service state:
```bash
systemctl --user status agentchattr-wrapper@claude.service
```

- Logs:
```bash
journalctl --user -u agentchattr-wrapper@claude.service -f
```

- Render status endpoint:

`https://agentchattr.onrender.com/api/status`

Your CLI agents should appear available once wrappers are healthy.
