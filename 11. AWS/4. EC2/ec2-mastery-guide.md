# AWS EC2 Mastery Path — For Engineers with IAM & VPC Experience

**Assumed background:** You know IAM (roles, policies, trust relationships) and VPC (subnets, route tables, IGW/NAT, NACLs) already. This path does not re-teach those, but every module tells you exactly where EC2 touches them.

**Format of each module:** `Concept → Why it matters in production → Hands-on Task → Assignment (graded by you)`

Work top to bottom. Don't skip modules just because a topic sounds "basic" — the goal is to close gaps, not just review.

---

## Module 0 — Environment Setup

**Task 0.1:** Set up one throwaway AWS account or a sandbox in your org's account. Install and configure AWS CLI v2 (`aws configure`) with a named profile, not default. Install `session-manager-plugin` for CLI-based SSM access (used later).

**Task 0.2:** Create a budget alert ($5–10 threshold) in AWS Budgets before you touch anything else. EC2 is the #1 source of "oops" bills.

---

## Module 1 — EC2 Core Concepts (Foundational, but go deep)

### 1.1 What EC2 actually is
- Virtual machines running on the **Nitro System** (AWS's hypervisor + custom silicon for networking/storage offload). Know that Nitro separates hypervisor, networking (Nitro Cards), and security (Nitro Security Chip) from the host CPU — this matters for security questions ("can AWS see my RAM?" — no, Nitro removes operator access).
- Instance lifecycle states: `pending → running → stopping → stopped → shutting-down → terminated`. Know the difference between **stop**, **stop-hibernate**, and **terminate**, and what happens to each attached resource (EBS persists on stop, instance store does NOT, public IP is released on stop unless EIP).

### 1.2 Instance Types & Families
- Naming convention: `m6i.large` → family(m) + generation(6) + processor variant(i = Intel, a = AMD, g = Graviton/ARM, none = default) + size.
- Families: **General Purpose** (M, T — T is burstable/credits-based), **Compute Optimized** (C), **Memory Optimized** (R, X, High Memory), **Storage Optimized** (I, D, H1), **Accelerated Computing** (P, G, Inf, Trn for GPU/ML).
- T-family burstable credits: understand CPU credit accounting, `unlimited` vs `standard` credit mode, and how sustained high CPU exhausts credits → throttling.

**Task 1.1:** Launch a `t3.micro`, a `t3.unlimited`-mode instance, and stress-test CPU with `stress-ng` on both. Watch CPU credit balance in CloudWatch (`CPUCreditBalance`, `CPUSurplusCreditBalance`). Document what happens when credits run out on `standard` mode.

**Task 1.2:** Use the AWS pricing/instance-selector or `aws ec2 describe-instance-types` to compare vCPU/memory ratio across an `m6i`, `c6i`, and `r6i` of the same size. Explain in your own words when you'd pick each.

**Assignment 1:** Given a workload description ("Java Spring Boot API, moderate steady CPU, 8GB heap, occasional spikes"), pick and justify an instance family + size using actual CLI-retrieved specs, not guesswork.

### 1.3 AMIs (Amazon Machine Images)
- Structure: root volume snapshot + block device mapping + launch permissions + product code (for marketplace AMIs).
- AMI types: AWS-provided, Marketplace, community, and **your own custom AMIs**.
- Golden AMI pattern for immutable infrastructure.

**Task 1.3:** Launch an instance, install/configure something (e.g., nginx + a custom index page), then create a custom AMI from it (`create-image`). Launch a new instance from that AMI and confirm it boots pre-configured.

**Task 1.4:** Copy that AMI to a second region. Note what does and doesn't carry over (snapshot IDs change, tags don't copy by default).

**Assignment 2:** Build a "golden AMI" pipeline manually: base AMI → CIS-hardening script via user data → new AMI → deregister the old one and clean up its snapshot. Write the deregistration + snapshot cleanup as a script (real cost leak in the wild: orphaned snapshots from old AMIs).

---

## Module 2 — Storage for EC2

### 2.1 EBS (Elastic Block Store)
- Volume types: `gp3` (baseline 3000 IOPS/125MB/s, independently provisionable), `gp2` (legacy, burst-credit based like T-instances), `io1/io2` (provisioned IOPS, io2 Block Express for sub-ms latency + higher durability), `st1`/`sc1` (throughput-optimized/cold HDD for sequential workloads).
- EBS is network-attached — even "local" disk I/O leaves the instance. Understand EBS-optimized instances and dedicated bandwidth.
- Snapshots are incremental, stored in S3 behind the scenes, and are **region-scoped** unless copied.
- Multi-Attach (io1/io2 only, specific clustered-filesystem use cases).
- Encryption: KMS-backed, can set account-level default encryption.

**Task 2.1:** Attach a `gp3` volume, benchmark it with `fio`, then modify IOPS/throughput live (`modify-volume`) without detaching, and re-benchmark. This is a key gp3 advantage over gp2 — no downtime to scale.

**Task 2.2:** Create a snapshot, then a snapshot lifecycle policy (Data Lifecycle Manager / DLM) that auto-snapshots daily and retains 7. Verify it fires (or simulate via manual run).

**Task 2.3:** Encrypt an existing unencrypted volume (trick question — you can't in-place; you must snapshot → copy-with-encryption → create volume → swap). Do the full swap on a running instance's non-root volume.

**Assignment 3:** Design (and implement) a backup/DR strategy for a fleet of 5 tagged instances: automated snapshots via DLM, cross-region copy of snapshots for at least one critical instance, and a documented restore procedure with RTO/RPO you define and justify.

### 2.2 Instance Store
- Ephemeral, physically attached to host, high IOPS, **data lost on stop/terminate/host failure**. Only appropriate for cache, scratch, replicated data (e.g., Kafka log segments already replicated elsewhere).

**Task 2.4:** Launch an instance-store-backed instance type (e.g., `i3.large` or `m5d.large`), write data to the instance store volume, stop/start the instance (if root is EBS) and confirm instance-store data behavior vs your EBS root data behavior.

---

## Module 3 — Networking for EC2 (builds on your VPC knowledge)

### 3.1 ENI (Elastic Network Interface)
- Primary vs secondary ENIs, attaching multiple ENIs per instance (limits vary by instance type), moving an ENI between instances for failover patterns.
- ENA (Elastic Network Adapter) and EFA (Elastic Fabric Adapter — for HPC/tightly-coupled MPI workloads, bypasses OS kernel).

**Task 3.1:** Attach a secondary ENI to a running instance in a different subnet (same AZ). Configure routing/`netplan`/`ip route` inside the OS to actually use it (this is the part people skip — attaching isn't enough, the OS needs routing rules).

**Task 3.2:** Detach that ENI and attach it to a second instance to simulate a manual failover. Time how long the "failover" takes.

### 3.2 Security Groups vs NACLs (you know NACLs from VPC — focus on the EC2-specific nuances)
- Stateful, instance/ENI-level, evaluated as allow-only (no explicit deny), referencing other SGs by ID (not just CIDR) for dynamic fleets.
- SG chaining pattern: ALB-SG → App-SG → DB-SG, each referencing the previous by SG-ID.

**Task 3.3:** Build the 3-tier SG chaining pattern above for a real (even if toy) ALB → EC2 → RDS/EC2-DB setup. Prove that direct internet access to the app tier is blocked but ALB access works.

### 3.3 Elastic IP & Public/Private IP behavior
- Public IP is dynamic and released on stop unless it's an EIP. EIP costs money when **not** attached to a running instance (a classic surprise cost).

**Task 3.4:** Allocate an EIP, associate/disassociate it, and check the Cost Explorer/Billing line item for an idle EIP to see the charge appear.

### 3.4 Placement Groups
- **Cluster** (low latency, single AZ, HPC/tightly coupled), **Spread** (max 7 per AZ per group, hardware isolation, for critical small clusters), **Partition** (large distributed systems like HDFS/Cassandra/Kafka, isolates partitions across racks).

**Task 3.5:** Launch 3 instances in a Spread placement group and 3 in a cluster placement group (same instance type). Use `describe-instances` to inspect placement info and explain, in your own words, which failure domains each protects against.

---

## Module 4 — Access, Bootstrapping & Automation

### 4.1 Key Pairs & Access Patterns
- Key pair injects public key via cloud-init on first boot only. Know how to rotate access on an already-running instance (you can't "add" a new key pair after launch through the console — must edit `~/.ssh/authorized_keys` manually or via SSM/user data on reboot).

**Task 4.1:** Launch an instance, then simulate "lost the .pem file" — recover access using EC2 Instance Connect or SSM Session Manager instead of SSH keys.

### 4.2 User Data & Instance Metadata Service (IMDS)
- User data runs once on first boot (cloud-init) unless you engineer persistence.
- IMDSv1 vs **IMDSv2** (token-required, session-oriented) — IMDSv2 exists specifically to block SSRF attacks that steal instance role credentials via `169.254.169.254`. Know how to enforce IMDSv2-only at launch template and account level.

**Task 4.2:** Write a user-data script that installs a web server, pulls config from S3 using the instance's IAM role (no hardcoded keys), and starts the service — all unattended.

**Task 4.3:** Demonstrate the SSRF risk: from inside an instance with IMDSv1 enabled, curl the metadata endpoint and retrieve temporary role credentials. Then enforce IMDSv2-only (`HttpTokens=required`) and show the same unauthenticated curl now fails.

### 4.3 Systems Manager (SSM) for EC2 — this is the modern replacement for a lot of "log in and do stuff"
- SSM Agent, Session Manager (no SSH keys/bastion needed, full IAM + CloudTrail audit trail), Run Command (execute scripts at scale without SSH), Patch Manager, State Manager (enforce configuration drift correction), Parameter Store (config/secrets, cheaper alternative to Secrets Manager for non-rotating values).

**Task 4.4:** Connect to an instance with **zero open inbound ports** (no SG rule for port 22 at all) purely via SSM Session Manager. This is the production-correct pattern — internalize it.

**Task 4.5:** Use Run Command to patch 3 instances simultaneously (`AWS-RunPatchBaseline` or a custom command document). Use Parameter Store to store a config value and retrieve it from user data at boot.

**Assignment 4:** Redesign a "bastion host + SSH key" access pattern into a fully SSM-based, keyless, bastion-less access model. Document the IAM policy needed and prove no inbound SG rule is required for administrative access.

---

## Module 5 — Scaling & High Availability

### 5.1 Launch Templates (know these cold — Launch Configurations are legacy/deprecated for new work)
- Versioning, mixing instance types/purchase options in one ASG via launch template overrides.

**Task 5.1:** Create a launch template with 2 versions (e.g., v1 = `t3.micro`, v2 = `t3.small` + updated AMI). Launch instances from each version explicitly, then set a default version.

### 5.2 Auto Scaling Groups (ASG)
- Min/Max/Desired, health checks (EC2 vs ELB health check type — this trips people up: EC2 health check only sees hypervisor-level failure, not app-level; ELB health check catches app failures), cooldown periods, lifecycle hooks (`Pending:Wait`, `Terminating:Wait` — for draining connections or running bootstrap steps before an instance is marked InService).
- Scaling policies: Target Tracking (simplest, e.g. keep CPU at 50%), Step Scaling, Scheduled Scaling, Predictive Scaling.
- Instance refresh (rolling replacement when launch template changes) vs manually terminating instances.
- Warm pools (pre-initialized stopped instances to cut scale-out latency).

**Task 5.2:** Build an ASG (min 2, max 6, desired 2) behind an ALB using ELB-type health checks. Load test with `hey`/`ab`/`locust` to trigger target-tracking scale-out on CPU. Watch it scale back in after load stops.

**Task 5.3:** Add a lifecycle hook on `Terminating` that gives the instance 60 seconds and sends an SNS notification before actual termination — simulate graceful connection draining.

**Task 5.4:** Trigger an **instance refresh** after updating the launch template (new AMI). Watch the rolling replacement with a min-healthy-percentage setting and confirm zero downtime via continuous curl against the ALB during the refresh.

**Assignment 5:** Take Assignment 4's SSM-only, no-SSH app tier and put it inside a fully automated ASG: new launch template version → instance refresh → zero manual SSH ever touches these boxes. Add a lifecycle hook that runs a smoke test before marking InService (`Pending:Wait` + a Lambda/SSM check that calls back `complete-lifecycle-action`).

### 5.3 Load Balancing (technically a separate service, but inseparable from EC2 at scale)
- ALB (L7, path/host routing, WAF integration) vs NLB (L4, static IP, ultra-low latency, preserve source IP) vs (legacy) CLB.
- Target Groups: instance-target vs IP-target vs Lambda-target, deregistration delay (connection draining timeout), stickiness.

**Task 5.5:** Configure an ALB with path-based routing to two different target groups running two different apps on the same ASG-managed fleet.

---

## Module 6 — Purchasing Options & Cost Optimization

### 6.1 Pricing Models
- **On-Demand**, **Reserved Instances** (Standard vs Convertible, 1yr/3yr, All/Partial/No Upfront — know that Standard RIs can't change instance family, Convertible can), **Savings Plans** (Compute SP = most flexible, EC2 Instance SP = deeper discount but locked to family/region), **Spot Instances** (up to 90% off, 2-minute interruption notice, Spot Fleet/ASG-with-mixed-instances for resilience), **Dedicated Hosts** vs **Dedicated Instances** (hosts give visibility into physical sockets/cores — needed for BYOL software licensing tied to physical cores).

**Task 6.1:** Launch a Spot Instance directly, then poll the instance metadata for the interruption-notice path (`/latest/meta-data/spot/instance-action`) — you won't get a real interruption on demand, but confirm the endpoint structure and write a shutdown script that would gracefully drain on that signal.

**Task 6.2:** Convert your Module 5 ASG to a **mixed instances policy**: base capacity on On-Demand, additional capacity on Spot across 3+ instance types, with `capacity-optimized` allocation strategy. This is the real-world cost-optimization pattern for fault-tolerant fleets.

**Assignment 6:** Given a fleet's last 30 days of usage (simulate with Cost Explorer or made-up steady numbers), calculate and justify: how much of it should be Savings Plan-covered vs on-demand vs Spot, and produce an actual purchase recommendation with numbers.

---

## Module 7 — Monitoring, Recovery & Troubleshooting

### 7.1 CloudWatch for EC2
- Default metrics (CPU, network, disk *bytes* — note EC2 does **not** natively report memory or disk *space* usage; requires the CloudWatch Agent) vs CloudWatch Agent metrics.
- Status checks: **System status check** (AWS infra problem — triggers auto-recovery) vs **Instance status check** (OS-level problem — does not auto-recover, needs your intervention or a recovery action you configure).
- EC2 Auto Recovery (CloudWatch alarm action on system status check failure → automatic stop/start on new hardware, preserves instance ID/IP/EBS).

**Task 7.1:** Install the CloudWatch Agent, push custom memory and disk-usage metrics, and build a dashboard.

**Task 7.2:** Create a CloudWatch alarm on **StatusCheckFailed_System** with a "recover" action. (You can't easily force a real hardware failure, but configure it correctly and document exactly what would happen and why recovery works — same instance ID, new host.)

### 7.2 Troubleshooting muscle memory
- Instance won't boot: check system log (`get-console-output`), check status checks, check security group/NACL if it boots but is unreachable, check IMDS/user-data script exit codes via `/var/log/cloud-init-output.log`.
- "Instance is running but app unreachable": SG → NACL → route table → OS firewall (iptables/firewalld) → app not listening on correct interface (0.0.0.0 vs 127.0.0.1) — walk this chain every time.

**Task 7.3:** Deliberately break an instance 3 different ways (wrong SG rule, app bound to localhost only, corrupted user-data script) and diagnose each using only `get-console-output`, CloudWatch, and SSM — no reboot-and-guess.

**Assignment 7:** Write a personal EC2 troubleshooting runbook/checklist from what you just did — this becomes your on-call reference.

---

## Module 8 — Advanced / Production-Grade Topics

- **Hibernation**: RAM state saved to encrypted EBS root volume on stop, near-instant resume with warm OS/app state. Requirements (encrypted root volume, size limits, supported AMIs/instance families).
- **Nitro Enclaves**: isolated compute environment for processing highly sensitive data with no persistent storage, no interactive access, no external networking — for cryptographic key handling.
- **Dedicated Hosts + License management**: bringing BYOL Windows/Oracle licensing tied to physical sockets/cores, host affinity for licensing compliance.
- **Bare Metal instances** (`.metal` suffix): direct hardware access, needed for workloads requiring hypervisor-level access (nested virtualization, specific licensing, hardware performance counters).
- **EC2 Fleet vs Spot Fleet vs ASG with mixed instances**: know when EC2 Fleet (one-time or ongoing request across On-Demand+Spot without ASG's lifecycle management) is the right tool vs a full ASG.
- **Capacity Reservations** (On-Demand Capacity Reservations, and Capacity Blocks for ML/GPU) — guaranteeing capacity in an AZ regardless of purchase option, decoupled from billing discounts (pair with Savings Plans for discount + guaranteed capacity).
- **Cross-account AMI sharing** and **RAM (Resource Access Manager)** for sharing across an AWS Organization.

**Task 8.1:** Enable hibernation on a new instance, hibernate it, and time the resume vs a cold start — measure actual difference in seconds.

**Task 8.2:** Share a custom AMI with a second AWS account (or simulate with a second sandbox) using explicit launch permissions, and launch from it cross-account.

**Assignment 8 (Capstone):** Design and build, end-to-end, a production-representative EC2 architecture for a fictional 3-tier web app:
1. Custom golden AMI (hardened, app pre-baked)
2. Launch template referencing that AMI, IMDSv2 enforced, SSM-managed (no SSH)
3. ASG with mixed instances policy (On-Demand base + Spot burst) across 2+ AZs
4. ALB with path-based routing and proper SG chaining to a private-subnet backend
5. CloudWatch Agent + custom dashboard + auto-recovery alarm + lifecycle hooks for graceful drain
6. EBS DLM backup policy + documented DR restore steps
7. A written cost breakdown: on-demand-equivalent cost vs your actual designed cost, with Savings Plan/Spot justification
8. A one-page architecture diagram and a README explaining every decision

Present this capstone as if defending it in a design review — for each component, be ready to answer "why this, and what did you rule out?"

---

## Suggested Pace
- Modules 0–2: 1 week (you'll move fast here given your background)
- Modules 3–4: 1 week
- Modules 5–6: 1.5 weeks (this is where most real production knowledge lives)
- Module 7: 3–4 days
- Module 8 + Capstone: 1–1.5 weeks

**Before moving to the next module, you should be able to explain each concept out loud without notes — if you can't, redo the task, don't just reread the theory.**
