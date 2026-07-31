# Motadata AIOps (ObserveOps) — Phase 1 Product Research

**Purpose:** Complete ground-truth overview of the Motadata AIOps/ObserveOps product — every module, every data type it ingests, every monitorable entity, and the full configuration surface — as the foundation for building a zero-dependency, minimal-configuration ingestion application on top of it.

**Sources:**
- Live appliance **https://172.16.14.71** (build 8.2.6, UI 8.0.11) — explored via browser automation; taxonomy pulled from the live API (`/api/v1/settings/objects/types`).
- Official documentation **https://docs.motadata.com/motadata-aiops-docs/** (803 pages crawled).

Researched: 2026-07-31.

---

## 1. Product Module Map

Top navigation of the live appliance (16 modules):

| Module | Route | What it does |
|---|---|---|
| **Dashboards** | `/dashboard` | Preset + custom dashboards, NOC View. Widget types: Chart (timeseries), Grid, Top N, Gauge, Heat Map, Sankey, Map (geo), Stream (live alerts), Event History, Free Text, iFrame. Widgets query metric, log, flow, trap, APM, RUM data. |
| **Monitors** | `/inventory/` | Central inventory of everything monitored. Inventory tabs: Network, SDN, Server & Apps, Storage, Virtualization, HCI, Database, Container Orchestration, Cloud, **Interface, WAN Link, Process, Container, Service**, Service Check, Other. Interfaces/processes/services are first-class monitored entities under a parent monitor. |
| **Alerts** | `/alerts/` | Alert list with severity classification, drill-down, correlation tabs, flap history, comments. |
| **SLO** (BETA) | `/slo/` | SLO tracking — APM / RUM / NetRoute performance SLOs, correction profiles, penalty profiles, SLO Explorer (OK/Warning/Breached). |
| **Reports** | `/reports/` | 150+ built-in reports across 9 tabs (Metric, Log, Flow, Trap, Audit, NCCM, APM, RUM, NetRoute) + Log Compliance (PCI-DSS, HIPAA, GDPR, SOX, ISO 27001). PDF/XLSX/HTML export, scheduling. |
| **Topology** | `/topology/network` | Auto-updating network topology + cloud/virtualization topology, fed by the Topology Scanner. |
| **NCCM** | `/nccm/` | Network Configuration & Compliance Management — config backup/versioning/restore, change detection, firmware upgrades, compliance benchmarks (CIS, GDPR, HIPAA, SOX). |
| **NetRoute** | `/netroute/` | Hop-by-hop network path monitoring (latency, loss, availability per hop), route-change detection. |
| **Metric Explorer** | `/metric-explorer/` | Ad-hoc metric exploration with ML: anomaly detection, outlier removal, forecast, compare-with-past, cross-stack correlation. |
| **Log Explorer** | `/log/` | Log search, live tail, ML pattern analysis, surrounding-context view. |
| **APM Explorer** | `/apm/` | Traces/spans/services, flame charts, service maps, error tracker, APM compare. |
| **RUM Explorer** | `/rum/` | Real-user sessions, Web Vitals (LCP/FCP/CLS/INP), frontend errors, Apdex, geo/device/browser breakdowns. |
| **Flow Explorer** | `/flow/` | Bandwidth/conversation analysis — group by up to 4 fields (src/dst IP/port), flow diagrams, top talkers. |
| **Trap Explorer** | `/trap-explorer/` | SNMP trap visualization and search. |
| **Audits** | `/audit/` | Audit trail of user actions and system changes. |
| **Settings** | `/settings/` | Full administration surface (see §5). |

---

## 2. Data Types Ingested — every pipeline into the platform

| # | Data type | How it gets in | Ports / protocols | Mapped to |
|---|---|---|---|---|
| 1 | **Metrics (polled)** | Agentless polling by collectors using credential profiles | SNMP :161, SSH :22, PowerShell/WinRM :5985/:5986, HTTP/HTTPS, JDBC, JMX, JMS, Telnet, Cloud APIs | Monitor + instances (interface, process, service, VM, disk…) |
| 2 | **Metrics (agent)** | **MotaAgent** push — down to 1-second polling, local store-and-forward buffering during outages | Agent → platform | Monitor (hostname identity) |
| 3 | **Logs — syslog** | Passive listener; devices point rsyslog/syslog at collector (`*.* @IP:port` UDP, `@@` TCP) | Syslog UDP/TCP | Log Inventory source, parser category |
| 4 | **Logs — agent** | MotaAgent tails application log files (directory + wildcard patterns, multiline regex) and Windows Event Logs (channels, levels, event IDs; 28 Windows Server roles documented) | Agent → platform | Log source |
| 5 | **Logs — agentless pull** | **Log Collection Profiles**: collection types **HTTP/HTTPS, SSH, Powershell, Database** + runbook-based collectors (observed live: AWS, Azure, O365 Exchange/SharePoint/General, vCenter Task, Windows Event, Cisco ACI Fault) with interval + timeout + parser + runbook | Varies | Log source |
| 6 | **Flows** | Passive listeners; device exports flow records | **sFlow v5 :6343, NetFlow :2055, BGP sFlow :6344, BGP NetFlow :2056** (live settings screen); docs also cover IPFIX, jFlow v5/8/9, Huawei NetStream, Citrix AppFlow, nProbe/YAF | Flow source device + interface; enriched via Application/Protocol/AS/Domain/Geolocation/IP mappings |
| 7 | **SNMP traps** | Passive **Trap Listeners** — multiple listeners, per-listener version + port (live: V1/V2c on 1620/162/161, V3 on 1630/1640) | UDP | Source monitor; trap policies |
| 8 | **APM traces** | MotaAgent language agents (Java, .NET, PHP, Node.js, Python, Go, C++, Ruby), custom-instrumentation SDKs, or **eBPF OBI** zero-code capture (Linux amd64, kernel 5.8+) | TCP **9474** & **9433** | Registered APM application → services → traces/spans |
| 9 | **RUM events** | Browser JS SDK; app registered first (live registration fields: name, type **React / Vue / Angular / Next.js / JS**, version, environment, session sample rate %, privacy **allow / mask-user-input**) | HTTPS from browser | Registered RUM application → sessions/views/vitals/errors |
| 10 | **Config backups (NCCM)** | SSH/Telnet CLI capture; config transfer via TFTP/FTP/SCP-SFTP; syslog-triggered change detection | SSH/Telnet | NCCM Device Inventory, versioned (default 15 versions) |
| 11 | **NetRoute path probes** | Active path probing per interval | ICMP/UDP | NetRoute monitors (per-path licensing) |
| 12 | **IP SLA** | Read from Cisco routers (ICMP Echo/Jitter/Path Echo via SNMP; UDP Echo/Jitter via SSH) | SNMP/SSH | IPSLA monitors on WAN links |
| 13 | **Audit/system events** | Internal | — | Audit Trail |

**Data retention defaults** (docs, System Settings → Data Retention): metrics raw 30d/agg 180d; logs raw 7d/agg 180d; flows raw 2d/agg 180d; traps raw 7d/agg 180d; alerts 90d; APM metric 180d, event raw 2d; NCCM 15 versions; NetRoute 7d; audit 30d.

**Metric catalog scale:** the live appliance exposes **9,371 metric counter keys** (`/api/v1/misc/column-mappers`, group.type=metric).

---

## 3. Monitorable Entity Catalog — ~175 object types (live API ground truth)

Pulled from the live appliance: `GET /api/v1/settings/objects/types?filter={"key":"object.category","value":[...]}`. This is the exact taxonomy the product uses for discovery + provisioning.

### Server (42 types)
Linux, Windows, Windows Cluster, Solaris, HP-UX, IBM AIX, IBM AS/400, Windows RDP, Cisco UCS,
Apache HTTP, Apache Tomcat, Microsoft IIS, HAProxy, Dotnet, WildFly, Oracle WebLogic, IBM WebSphere,
Active Directory, Windows DNS, Windows DHCP, Linux DHCP, Bind9, Zimbra,
Exchange Mailbox, Exchange Mailbox Role, Exchange Client Access Role, Exchange Edge Transport Role,
Microsoft Dynamics CRM, IBM MQ, Apache MQ, MSMQ, RabbitMQ,
Oracle Database, SQL Server, MySQL, MariaDB, PostgreSQL, MongoDB, IBM Db2, Sybase, SAP HANA, SAP MaxDB
*(databases appear under both Server and Database categories)*

### Database (13 types)
Oracle Database, Oracle RAC Cluster, SQL Server, MySQL, MariaDB, PostgreSQL, MongoDB, Redis DB, Elasticsearch, IBM Db2, Sybase, SAP HANA, SAP MaxDB

### Cloud (56 types)
- **AWS (21):** AWS Cloud, EC2, EBS, EFS, S3, RDS, DynamoDB, DocumentDB, Lambda, ECS, EKS, ECR Public/Private Repository, ELB, Auto Scaling, Elastic Beanstalk, Backup, SNS, SQS, CloudFront, HTTP/REST/WebSocket API Gateways
- **Azure (14):** Azure Cloud, VM, VM Scale Set, WebApp, Function, Storage, SQL Database, MySQL Server, PostgreSQL Server, Cosmos DB, Load Balancer, Application Gateway, CDN, Service Bus
- **GCP (8):** Google Cloud, Compute Engine, GKE, Cloud Storage, Filestore, SQL Server, MySQL, PostgreSQL
- **OCI (6):** Oracle Cloud, Compute Instance, Block Volume, File Storage, Object Storage, ALB
- **Microsoft 365 (5):** Office 365, Exchange Online, SharePoint Online, OneDrive, Microsoft Teams

### Network (17 types)
Router, Switch, Firewall, Load Balancer, Wireless Controller, SNMP Device (generic/custom), Linux (SNMP), Windows (SNMP), Printer, UPS, Hardware Sensor, Email Gateway, Cisco Wireless, Aruba Wireless, Ruckus Wireless, Ruijie Wireless, Extreme Wireless
- **Vendor coverage (docs):** Routers — Cisco, Juniper, Huawei, H3C, Mikrotik, D-Link, Radware, AlaxalA. Switches — Cisco, Juniper, Huawei, H3C, Mikrotik, Dell, D-Link, Netgear, HP, Extreme, Brocade, Radware, Apresia, Alteon, AlaxalA. Firewalls — Cisco ASA, Juniper, FortiGate, Palo Alto, Check Point, SonicWall, WatchGuard, Barracuda, Cyberoam, Pulse Secure. Load balancers — F5, Radware, NetScaler. UPS — APC, APC NetBotz, Eaton, Emerson, Schneider, Delta, CyberPower, Tripp Lite, Toshiba, Socomec, Phoenixtec, Valere, Digipower, Cayman, Arris.

### SDN (10 types)
Cisco ACI, Cisco Meraki (+ Meraki Switch, Meraki Radio, Meraki Security), Cisco vManage, vSmart, vBond, vEdge (Catalyst SD-WAN), VMware NSX-T

### Virtualization (10 types)
vCenter, VMware ESXi, Legacy ESXi, Hyper-V, Hyper-V Cluster, KVM, Citrix Xen, Citrix Xen Cluster, Proxmox VE, Proxmox VE Cluster

### HCI (2 types)
Nutanix, Prism

### Storage (17 types)
NetApp ONTAP Cluster, Dell EMC Unity, Dell EMC VNX Processor, Dell EMC VNX Control Station, HPE 3PAR, HPE Primera, HPE MSA 2060, HPE StoreOnce, IBM FlashSystem, IBM Tape Library (under Other), Huawei OceanStor, Hitachi VSP E Series, QNAP TS, QSAN XCubeNXT, Synology Rack Station, Fibrenetix E88, Harmonic Content Server, Harmonic Content Store
- Out-of-band hardware management (docs): Dell iDRAC, HPE iLO.

### Container Orchestration (3 types)
Kubernetes, OpenShift Kubernetes, Tanzu Kubernetes (+ Docker containers, GKE/EKS via cloud)

### Service Check (11 types)
Ping, Port (TCP/UDP), URL, REST API, DNS, Domain (expiry), SSL Certificate, Email (SMTP/POP3/IMAP), FTP, NTP, RADIUS

### Wireless
Category exists but types live under Network (Cisco/Aruba/Ruckus/Ruijie/Extreme Wireless + Meraki under SDN). Licensed 1 per 2 APs.

### Flow-export device coverage (docs — 114 per-device configuration guides)
Cisco (~40 device families: ISR, Catalyst 2960X→9300, Nexus 3K–9K, ASR, NCS, ASA, AVC, vEdge, WLC), Juniper (jFlow MX/SRX, EX sFlow), Huawei (NetStream, sFlow, CE), Fortinet, HPE/Aruba, H3C, Mikrotik, Extreme/Enterasys, Brocade, Check Point, WatchGuard, Riverbed, NetScaler AppFlow, VMware vSphere VDS, Ubiquiti, ZTE, Zyxel, Nortel, Netgear, D-Link, Dell, Adtran, Allied Telesis, Avaya, Blue Coat, Edge-Core, Force10, Foundry, nProbe, YAF, and more.

---

## 4. Discovery & Ingestion Configuration Surface

### 4.1 Credential Profiles — 10 protocols (live, complete)
**Powershell, SNMP V1/V2c, SNMP V3, SSH, JDBC, HTTP/HTTPS, Cloud, JMX, JMS, Telnet**
- SNMP v3: security user, level, auth+privacy protocols/passwords. SSH: password or key+passphrase, enable-mode options. PowerShell: WinRM :5985/:5986. HTTP/HTTPS: basic auth or API key (Meraki). Cloud: AWS access/secret key + IAM policy; Azure/O365 client ID + tenant ID + secret; GCP OAuth (client ID/secret/auth URL/token URL/scope); OCI tenancy OCID/user OCID/private key/fingerprint. Client certificates for OpenShift/Tanzu. All profiles have a **Test** button.

### 4.2 Discovery Profiles (live create form)
- **Category tabs:** Server (Linux/Unix, Windows), Cloud, Network, SDN, Virtualization, HCI, Storage, Database, Service Check, Wireless, Container Orchestration, Other
- **Target formats:** IP/Host, IP Range, CIDR, CSV upload
- **Fields:** Collector Type + Collectors (multi-select → load balancing/failover), Groups, Credential Profiles (multiple), Tags, Port, Ping Check toggle, Notifications
- **Run modes:** Save & Exit / Save & Schedule (daily/weekly/monthly/once) / Save & Run; auto-provisioning option; Rediscover Settings pick up new instances/services later
- Built-in help card per type: Supported Platforms, Network & Connectivity Requirements, Credential Requirements & Permissions, Discovery Mechanisms

### 4.3 Agent vs Agentless
- **Agentless (default):** collectors poll via the 10 credential protocols.
- **MotaAgent:** Windows + Linux; 1s polling; offline buffering; carries metrics + log tailing + Windows events + APM traces; eBPF zero-code APM on Linux.

### 4.4 Platform architecture (live Deployment Settings + docs)
- Components: **APP** (application/UI), **DATASTORE** (MotaStore DB), **Observer** (config sync), **Collectors** (remote pollers, selectable per discovery profile). Live box runs APP + DATASTORE standalone.
- Deployment modes: Single-Box, Distributed, Multi-Site (branch collectors), HA (VIP + heartbeat), DR, HA-over-WAN.

---

## 5. Settings Screen — complete tree (live appliance, 18 sections)

- **My Account:** My Profile, UI Preference, License
- **User Settings:** User, User Profile (RBAC roles), Personal Access Token, Role, Group, Password Settings, LDAP, Single Sign-On, Radius
- **System Settings:** Two Factor Auth, Mail Server, Proxy Server, SMS Server, Rebranding, Data Retention, **Deployment Settings** (collectors), MAC Address List, Storage Profile, Backup Profile, Rule Based Tags, DNS Server Profile, SSH Security Settings
- **Policy Settings (8 policy engines):** Metric, Log, Flow, Trap, NetRoute, APM, Network Config, RUM
- **Discovery Settings:** Credential Profile, Discovery Profile
- **Monitor Settings:** Device Monitor, Cloud Monitor, Monitor Templates, Agent Monitor, Service Check Monitor, Process Monitor, Service Monitor, File/Directory, **SNMP Device Catalog** (custom OID→template repo), Rediscover, NetRoute, Topology Scanner, Monitoring Hour, Custom Monitoring Field
- **Network Config Settings (NCCM):** Device Inventory, Device Template, Firmware Update Profile
- **Compliance Settings:** Compliance Policy, Benchmark, Rules
- **SNMP Trap:** Trap Profile, Trap Forwarder, Trap Listener (multi-listener, per-version/port)
- **Log Settings:** Log Inventory, Log Parser Library (Regex/JSON/Delimiter/Custom-Plugin parsers), Log Collection Profile, Log Forwarder (TCP/UDP, Raw/JSON/CEF, pre-filters)
- **Flow Settings:** Flow ports/aggregation/direction, Sample Rate, Application / Protocol / AS / Domain / Geolocation / IP Mappings
- **Plugin Library:** Runbook, Metric plugins (HTTP/SSH/PowerShell/DB/SNMP/Custom), Topology plugins, Log Parser plugins
- **Dependency Mapper:** Parent-Child Dependency Mapper
- **SLO (BETA):** SLO Profile, Correction Profile, Penalty Profile
- **Utility:** Ping, SNMP Ping, Traceroute, SNMP Walk, SNMP Community Check, MAC Address Resolver, CLI Command, PowerShell Command, DNS Resolver, Telnet
- **APM:** Application Registration
- **Real User Monitoring:** Application Registration (route: `/digital-experience-monitoring/rum-applications`)
- **Integration:** Integration Profile, Motadata ServiceOps, ServiceNow, Atlassian Jira, Microsoft Teams, Slack, LAMA

---

## 6. AIOps / Correlation Capabilities

- **Policy engine:** 8 basic policy types (one per data stream) + 2 AI/ML types — **Anomaly Policy** (statistical anomaly detection) and **Forecast Policy** (trend prediction). Threshold conditions over timeframes; per-severity runbook execution; notification with macros (`$$object.ip$$`, `$$severity$$`); escalation.
- **Severity model:** Critical, Major, Warning, Clear, Down.
- **Alert correlation (metric alerts):** 4 tabs — Correlated Metrics (process-level), Correlated Logs, Correlated Alerts (same device/window), Log Pattern (recurring signatures); alert flap history.
- **Metric Explorer ML:** anomaly, outlier removal, forecast, compare-with-past, cross-stack correlation.
- **Runbook automation:** SSH / PowerShell / SNMP / HTTP / Database / Telnet / TraceRoute / Custom; alert-triggered (per-severity), scheduled, or manual. Inbuilt: VM start/stop (Xen/ESXi/Hyper-V), process kill (Win/Linux), top-10 processes, service start/stop, ping, traceroute, SNMP next hop.
- **Notification channels:** Email, SMS, Microsoft Teams, Slack, Telegram, WhatsApp, in-app; alert forwarding as SNMP trap or syslog (RFC5424/3164, TCP/UDP, TLS).
- **ITSM:** Motadata ServiceOps (bidirectional incidents), ServiceNow, Jira (workflow-aware, auto-close on clear).

---

## 7. Licensing model (docs)

1 license per network device / server / VM / application / database / storage / WAN link / NetRoute; 1 per 2 wireless APs; **interfaces, processes, services free**; Log & Flow licensed **per GB/day**; APM per instrumented app instance; NCCM per managed device.

---

## 8. Implications for the Phase-2 "minimal-config ingestion" application

Observed friction points in the current product that a zero-dependency ingestion app can target:

1. **Config chain is long:** credential profile → discovery profile → run discovery → provision → monitor → policies. Minimum ~4 screens before first metric. An opinionated app could collapse this to one step (auto-detect protocol, auto-select credential).
2. **Taxonomy is API-accessible:** `/api/v1/settings/objects/types` (+ `object.category` filter) gives the full 175-type catalog; `/api/v1/misc/column-mappers` gives all 9,371 metric keys — everything needed to auto-generate ingestion configs programmatically.
3. **Passive pipelines need zero platform config** (syslog, flow, trap listeners are just ports) — the config burden is device-side; an app could generate device-side snippets per vendor (docs contain 114 flow guides worth of patterns).
4. **Every settings entity is REST-backed** (`/api/v1/settings/credential-profiles`, `/discoveries`, `/objects/types`, `/remote-event-processors`, `/tags`, `/integration-profiles`…) — full automation of onboarding is feasible without UI.
5. **Correlation hooks exist per stream** (8 policy types + anomaly/forecast) but are configured separately per stream — a unified cross-stream correlation config is a genuine gap.
