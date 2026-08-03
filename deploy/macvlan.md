# Macvlan — giving components their own LAN IPs

Motadata discovers **IP endpoints**. To make one VM look like a full estate, the databases and
simulated devices each get a real IP on your LAN via a Docker **macvlan** network. Without this
everything shares the VM's IP and Motadata sees one host instead of ~20 devices.

## 1. Create the network (once, on the VM)

Find the parent interface and your subnet:

```bash
ip -br addr            # e.g. ens160  UP  172.16.14.55/24
ip route | grep default # e.g. default via 172.16.14.1
```

Create the network, reserving a block of **free** IPs (confirm with your network team that
`aux_addresses`/the range is not in DHCP scope):

```bash
docker network create -d macvlan \
  --subnet=172.16.14.0/24 \
  --gateway=172.16.14.1 \
  --ip-range=172.16.14.96/27 \        # .96–.127 for containers
  -o parent=ens160 \
  shopverse-lan
```

> Replace the subnet/gateway/parent with your real values, and the range with the free block
> you were given. `/27` = 32 addresses, enough for the DBs + device fleet.

## 2. Assign IPs

Add a `docker-compose.macvlan.yml` overlay (values from `forge/shopverse.yaml`):

```yaml
name: shopverse
services:
  postgres:
    networks: {shopverse-lan: {ipv4_address: 172.16.14.100}, default: {}}
  mysql:
    networks: {shopverse-lan: {ipv4_address: 172.16.14.101}, default: {}}
  mongo:
    networks: {shopverse-lan: {ipv4_address: 172.16.14.102}, default: {}}
  redis:
    networks: {shopverse-lan: {ipv4_address: 172.16.14.103}, default: {}}
  rabbitmq:
    networks: {shopverse-lan: {ipv4_address: 172.16.14.104}, default: {}}
  snmpsim:
    networks: {shopverse-lan: {ipv4_address: 172.16.14.110}, default: {}}
networks:
  shopverse-lan:
    external: true
  default: {}
```

Run with all three files:

```bash
docker compose -f docker-compose.yml -f docker-compose.devices.yml \
               -f docker-compose.macvlan.yml up -d
```

## 3. The macvlan host-access caveat

A macvlan container **cannot reach the host it runs on** (and vice versa) — that's a kernel
limitation, not a misconfiguration. It does not affect Motadata (the appliance is a different
machine), but if the VM itself needs to reach these IPs, add a macvlan shim:

```bash
sudo ip link add shopverse-shim link ens160 type macvlan mode bridge
sudo ip addr add 172.16.14.95/32 dev shopverse-shim
sudo ip link set shopverse-shim up
sudo ip route add 172.16.14.96/27 dev shopverse-shim
```

Persist it via a systemd unit or `/etc/network/interfaces.d` if you want it across reboots.

## 4. Multiple device identities from one snmpsim

snmpsim serves a different device per **community string** (one `.snmprec` file each), so a
single container with one IP can present router/switch/firewall/UPS/printer profiles. Use
separate IPs only when you want them to appear as distinct devices in topology — in that case
run one snmpsim container per IP, each with its own data subset.

Place recordings in `deploy/devices/snmpsim-data/` as `<community>.snmprec`. Public snapshot
sets are available from the snmpsim project; you can also record a real device with
`snmprec.py --agent-udpv4-endpoint=<device-ip> --community=<c> --output-file=<name>.snmprec`.
