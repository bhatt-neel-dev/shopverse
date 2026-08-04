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

---

## Write-path findings (verified 2026-08-04 by creating + deleting real objects on 172.16.14.71)

All four payload shapes below were **POSTed for real** and returned `200 … created successfully`,
then deleted. Create responses put the new id at the **top level** of the body
(`{"response-code":200,"status":"succeed","message":"…","id":113285797781}`), not under `result`.

| Object | Endpoint | Result |
|---|---|---|
| Credential profile | `POST /settings/credential-profiles` | works as documented above |
| Discovery profile | `POST /settings/discoveries` | works; `discovery.credential.profiles` must hold the real credential **id** |
| Metric policy | `POST /settings/metric-policies` | works as documented above |
| Log parser | `POST /settings/log-parsers` | **needed one extra field** — see below |

### Log parser requires `log.parser.event`

Without it the API rejects the create:

```
400 MD022  "Missing information: Event is a required field"
```

`log.parser.event` is a **sample log line** the parser is derived from. For the ShopVerse JSON
schema, send one representative line, and give each entry in `log.parser.fields` the matching
`log.parser.field.value` taken from that sample:

```json
"log.parser.event": "{\"ts\":\"2026-08-04T10:00:00.123Z\",\"level\":\"INFO\",\"svc\":\"catalog\", … }",
"log.parser.upload": "no",
"log.parser.fields": [
  {"log.parser.field.name":"ts","log.parser.field.type":"timestamp","log.parser.field.value":"2026-08-04T10:00:00.123Z"},
  {"log.parser.field.name":"svc","log.parser.field.type":"none","log.parser.field.value":"catalog"}
]
```

### DELETE on a policy is a soft delete

`DELETE /settings/metric-policies/{id}` returns `200 … deleted successfully`, but the row stays in
`GET /settings/metric-policies` with `"policy.archived": "yes"`. Existence checks must therefore
**ignore archived rows**, or a re-run will think an archived policy is still configured and skip
recreating it. Credential profiles, discoveries and log parsers are hard-deleted and disappear.

### Encrypted login (build 8.2.7+)

`POST /api/v1/token` with a plaintext password fails `400`. Fetch `GET /api/v1/login-metadata`
→ `public.key` (PEM), encrypt the password with **RSA-OAEP-SHA256**, base64 it, and send
`{"user.name": "<plain>", "user.password": "<base64 cipher>"}` with no `encrypted` marker.
A wrong password then returns `401 MD021 Invalid Credentials` with a `login.attempts.left`
counter — do not brute force, the account locks.

### SNMP community key is `snmp.community`

A credential context of `{"snmp.version": "v2c", "community": "..."}` is accepted with
`200 created successfully`, but the appliance then polls with an **empty community**. Captured
with `tcpdump -n udp port 161` on the target while a discovery ran:

```
IP 172.16.14.71.45080 > 172.20.21.25.161:  C="" GetRequest(28)  .1.3.6.1.2.1.1.2.0
```

The correct key follows the `snmp.*` convention used by the other fields
(`snmp.version`, `snmp.security.level`, `snmp.security.user.name`):

```json
"credential.profile.context": { "snmp.version": "v2c", "snmp.community": "shopverse" }
```

The HTML form input is named `community`, which is misleading — that is not the API key.
Because GET redacts secrets, this is invisible from the API and only shows up on the wire.

### Database discoveries need `database` in the context

PostgreSQL and MySQL discoveries fail without it; every working profile on the appliance
carries one. The context also repeats the type and disables the ICMP pre-check:

```json
"discovery.context": {"port": 5432, "database": "shopverse",
                      "ping.check.status": "no", "discovery.object.type": "PostgreSQL"}
```

### Provisioning — discovery alone creates nothing

A discovery profile only *finds* objects; each one stays `object.state: "UNPROVISION"` (or
`"NEW"`) until it is provisioned, and **no monitor exists until then**. Two calls:

```
GET  /api/v1/settings/discoveries/{id}/result     → the discovered objects
POST /api/v1/settings/objects/provision
     {"params": [ <those objects, echoed back verbatim> ],
      "id": <discovery id>, "ui.event.uuid": "<uuid>"}
```

The result rows must be sent back unchanged — they carry `object.ip`, `object.host`,
`object.type`, `object.context`, `object.credential.profile` and the internal `id`.

The response is **`200 "Object provisioning started successfully"` — it is asynchronous**, so
the call returning 200 does not mean a monitor exists. Poll the discovery result and watch
`object.state` flip to `PROVISION`.

Monitors are listed via `POST /api/v1/settings/objects/search` with
`{"page.number": N, "page.size": 100}` — the result is an **object** (`items`, `total`,
`total.pages`), not an array, and paging must be walked to find a specific host.

#### Provisioning can silently no-op (observed 2026-08-04 on 172.16.14.71)

`POST /settings/objects/provision` returned `200 "Object provisioning started successfully"`
for every object, but:

| Profile | object.state after | monitor created |
|---|---|---|
| shopverse-postgresql / mysql / mongodb | `PROVISION` | **no** |
| shopverse-host-linux | stays `UNPROVISION` | no |
| shopverse-host-snmp | stays `NEW` | no |

The appliance held 441 monitors and **none** for the target IP, so even the objects marked
`PROVISION` never materialised.

This is **not** a payload problem. Clicking the appliance's own *Add Selected Objects* button
in its UI produces the identical outcome — `200 … started successfully`, no toast, state
unchanged. The discovery profile also carries exactly the same field set as other users'
profiles on the same box that did produce monitors, and no collector field exists on either.

So: a 200 from this endpoint means *queued*, not *done*, and the queue can fail silently.
Always verify by polling `object.state` **and** confirming the monitor exists via
`POST /settings/objects/search`. When both stall, the problem is appliance-side (provisioning
worker / collector), not the request.

#### The silent no-op is an `object.name` collision

Root cause of the section above, found by Neel. Every discovery profile pointed at one host
returns the object under the **same `object.name`** — the hostname. The first profile to be
provisioned claims that name; every later one is rejected as a duplicate, and the rejection is
silent: `200 "Object provisioning started successfully"`, no toast, `object.state` unchanged.

Fix: qualify `object.name` per profile before posting, e.g. `shopverse-linux`,
`shopverse-snmp`. The rest of the row is echoed back unchanged.

Verified: with unique names, all four monitors appear and poll **Up** —
`shopverse-linux` (Linux), `shopverse-snmp` (Linux (SNMP)), `shopverse` (MySQL),
`172.20.21.25` (MongoDB).

Also note `POST /settings/objects/search` accepts a **`search`** term
(`{"search": "shopverse", "page.size": 100}`). Use it — walking pages client-side is slow and
easy to get wrong.

### Renaming a live monitor

```
PUT /api/v1/settings/objects/{id}   {"object.name": "shopverse-mongodb"}
→ 200 {"message": "Monitor updated successfully", "id": ...}
```

A partial body is fine — only the supplied keys change, and the monitor keeps polling (status
stayed `Up` across the rename). Find the id via `POST /settings/objects/search`.

Note the inventory grid's own search body uses **`search.filter`**, not `search`:

```json
{"search.filter": "172.20.21.25", "filters": {}, "page.size": 50, "page.number": 0,
 "search.columns": ["object.name","object.ip","object.type","object.host","status", ...]}
```
