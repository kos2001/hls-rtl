# Hermes Agent Skills

Skills the RTL assistant loads on the Hermes Gateway. **This directory is the
source of truth** — the gateway profile under `~/.hermes/profiles/<profile>/skills/`
is a deploy target, so skills stay reviewable in git rather than living only in a
dotfile tree.

| Skill | Grounds the agent in |
|---|---|
| `gamma-bitexact-verification` | the DUT contract, the Δ-propagation drill, the append-only test set, how to read a sign-off verdict |
| `rtl-verification-opensource` | tool selection across verilator / icarus / cocotb / pyuvm / yosys / sby / verible / MCY, with each tool's limitation |
| `eda-transcript-conventions` | the severity-tagged message format the workbench transcript renders |

## Install / update

```sh
python scripts/sync_hermes_skills.py --list      # what the serving profile has
python scripts/sync_hermes_skills.py --dry-run   # what would change
python scripts/sync_hermes_skills.py             # install (additive)
python scripts/sync_hermes_skills.py --force     # overwrite, backing up first
```

The script resolves the profile actually serving `HERMES_GATEWAY_BASE_URL` (via the
listening socket), installs every skill here, and back-fills stock skills
(`systemverilog`, `fpga`) from another local profile that already ships them.
It never deletes, and backs up any file it replaces.

Verify from the running api-server:

```sh
curl -s localhost:8012/api/skills | python -m json.tool
```

`source: "repo-only"` means the skill is authored here but not yet synced — the
agent cannot load it. The workbench's Design Navigator shows the same state.

## Why discovery instead of a hard-coded list

The gateway serves **one** profile. Naming a skill the profile does not have tells
the agent to load something that does not exist — it either ignores the directive
or invents the guidance, with no error anywhere. `api/skills.py` therefore resolves
the live profile and builds the directive from what is really installed.
