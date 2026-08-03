# Motadata REST — verified object schemas

Captured live from 172.16.14.71 (build 8.2.6 / REP 8.2.7) on 2026-08-03 by GETting real objects.
These are the **actual** field names — several differ from what the docs/UI labels imply.

Auth: `Authorization: Bearer <PAT>` (Settings → User Settings → Personal Access Token).
All responses wrap payload in `{"response-code":200,"status":"succeed","result":[...]}`.

## Working endpoints (GET verified)

| Object | Endpoint | Count seen |
|---|---|---|
| Credential profiles | `/api/v1/settings/credential-profiles` | 511 |
| Discovery profiles | `/api/v1/settings/discoveries` | 533 |
| Metric/availability/anomaly/forecast policies | `/api/v1/settings/metric-policies` | 196 |
| Log parsers | `/api/v1/settings/log-parsers` | 140 |
| Log collectors (= "Log Collection Profile") | `/api/v1/settings/log-collectors` | — |
| Groups | `/api/v1/settings/groups` | 59 |
| Collectors / REPs | `/api/v1/settings/remote-event-processors` | 2 |
| Object type catalog | `/api/v1/settings/objects/types` | ~175 |

**403 (not these paths):** trap listeners, RUM apps, APM apps, log policies. Their UI screens
issue no REST calls on load, so they likely ride the event-bus/websocket. Still to be found.

## Credential profile

```json
{
  "credential.profile.name": "shopverse-linux-ssh",
  "credential.profile.protocol": "SSH",
  "credential.profile.context": { "username": "user", "password": "...", "cli.enabled": "no" }
}
```
Context per protocol (**`username`, not `user.name`**):
- `SSH` → `{username, password, cli.enabled: "no"}` (+ key/passphrase variants)
- `SNMP V1/V2c` → `{snmp.version: "v2c", community: "..."}`
- `SNMP V3` → `{snmp.version: "v3", snmp.security.level, snmp.security.user.name, ...}`
- `JDBC` → `{username, password}`
- `Powershell` → `{username, password}`

Protocols: `Powershell, SNMP V1/V2c, SNMP V3, SSH, JDBC, HTTP/HTTPS, Cloud, JMX, JMS, Telnet`.

## Discovery profile — **schema is `discovery.*`, not `discovery.profile.*`**

```json
{
  "discovery.name": "shopverse-host-linux",
  "discovery.type": "ip.address",
  "discovery.target": "172.16.14.99",
  "discovery.target.name": "172.16.14.99",
  "discovery.category": "Server",
  "discovery.object.type": "Linux",
  "discovery.context": { "port": 22, "ping.check.status": "yes" },
  "discovery.credential.profiles": [54280733030],
  "discovery.groups": [],
  "discovery.user.tags": [],
  "discovery.exclude.targets": [],
  "discovery.exclude.target.type": "ip.address",
  "discovery.config.management.status": "no",
  "discovery.scheduler": "no"
}
```
- `discovery.type`: `ip.address` | `ip.address.range` (e.g. target `172.16.8.1-255`) | CIDR | CSV
- **`discovery.credential.profiles` takes numeric IDs, not names** — credentials must be created
  first and their ids captured.
- `discovery.category` must match the object-type's category (Server/Network/Database/…).

## Policy (metric / availability / anomaly / forecast)

```json
{
  "policy.name": "shopverse-cpu",
  "policy.type": "Metric Threshold",
  "policy.state": "yes",
  "policy.title": "$$$severity$$$ - $$$object.name$$$",
  "policy.message": "$$$counter$$$ entered $$$severity$$$ with value $$$value$$$ on $$$object.host$$$($$$object.ip$$$)",
  "policy.context": {
    "metric": "system.cpu.percent",
    "filters": {"data.filter": {}},
    "entities": [],
    "policy.severity": {"CRITICAL": {"policy.condition": ">=", "policy.threshold": "85"}},
    "policy.trigger.time": 300,
    "policy.trigger.occurrences": 1,
    "policy.auto.clear.timer.seconds": 0
  },
  "policy.actions": {"Integration": {}, "Notification": {"Email": {}, "channels": {}}},
  "policy.archived": "no", "policy.renotify": "no", "policy.scheduled": "no"
}
```
- `policy.type` ∈ `Availability | Metric Threshold | Metric Baseline | Metric Anomaly | Forecast | Trace Metrics`
- Availability policies use `policy.context.metric` like `interface~status` plus
  `instance.type`/`policy.instance`, and no `policy.severity` block.
- Macros are **triple-dollar**: `$$$severity$$$`, `$$$object.ip$$$`, `$$$counter$$$`, `$$$value$$$`.
- `policy.metric.plugins` is a list of plugin ids scoping the policy; omit to leave unscoped.

## Log collector ("Log Collection Profile")

```json
{
  "log.collector.name": "shopverse-http",
  "log.collector.type": "ssh",
  "log.collector.state": "yes",
  "log.collector.interval": 10,
  "log.collector.timeout": 60,
  "log.collector.runbook": 10000000000050,
  "log.collector.log.parsers": [10000000000004]
}
```
Types: `http/https | ssh | powershell | database`. Parsers/runbooks referenced **by id**.

## Log parser

```json
{
  "log.parser.name": "ShopVerse JSON",
  "log.parser.type": "json",
  "log.parser.source.type": "Other",
  "log.parser.condition": "all",
  "log.parser.fields": [
    {"log.parser.field.name": "timestamp", "log.parser.field.type": "timestamp",
     "log.parser.field.value": "..."}
  ],
  "log.parser.date.time.format": "yyyy-MM-dd'T'HH:mm:ss.SSSXXX",
  "log.parser.date.time.formatter.type": "formatter"
}
```
`log.parser.type` is lowercase (`regex`, `json`, `delimiter`). Regex parsers additionally carry
`regex`, `log.parser.event` (the sample line) and `log.parser.log.positions`.

## Ordering for a fresh instance

1. credential profiles → capture ids
2. groups/tags (optional) → capture ids
3. discovery profiles (reference credential ids) → run → monitors get provisioned
4. log parsers → capture ids → log collectors (reference parser ids)
5. policies (reference metrics; entities empty = all monitors)
6. trap listeners / RUM+APM apps — endpoints TBD
