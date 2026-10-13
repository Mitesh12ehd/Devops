# Secrets on EC2: Step-by-Step Course

**Level:** You know IAM, VPC, basic EC2 and IMDS.
**Time:** about 6 to 8 hours including all labs.
**Cost:** a few cents if you clean up (Part 14).

## How to use this course

1. Read one Part at a time.
2. Do the **"Try it"** box before moving on.
3. Do the **assignments** in Part 12 in order.
4. Check your quiz answers in Part 13 (answer key at the very end).

Rule: **if you can't do the lab, you haven't learned it yet.** Come back to the Part.

## Contents

| Part | Topic |
|---|---|
| 0 | Words you need (glossary) |
| 1 | What is a secret, and why is it hard? |
| 2 | Bad places to keep secrets (with demos) |
| 3 | The big idea: fetch at runtime |
| 4 | Building blocks: role, IMDS, KMS (quick recap) |
| 5 | SSM Parameter Store |
| 6 | Secrets Manager |
| 7 | Permissions: the two locks (IAM + KMS) |
| 8 | Rotation (deep dive) |
| 9 | Writing the application code |
| 10 | Network path: VPC endpoints |
| 11 | Auditing and detection |
| 12 | **Assignments / Labs** |
| 13 | Quiz |
| 14 | Cleanup |
| 15 | Cheat sheet |
| 16 | Answer key |

---

# Part 0: Words You Need

| Word | Plain meaning |
|---|---|
| **Secret** | Anything that gives access if stolen: DB password, API key, private key, token |
| **Instance profile** | The "container" that attaches an IAM role to an EC2 instance |
| **Role credentials** | Temporary keys (`ASIA...` + token) the instance gets from IMDS |
| **ARN** | The unique address of an AWS resource |
| **KMS** | AWS service that holds encryption keys and does the encrypting and decrypting |
| **CMK / customer managed key** | A KMS key *you* create and control |
| **AWS managed key** | A KMS key AWS creates for a service (e.g. `aws/secretsmanager`) |
| **Rotation** | Changing a secret regularly, automatically |
| **Staging label** | A tag on a secret version, like `AWSCURRENT` |
| **VPC endpoint** | A private door from your VPC to an AWS service, no internet needed |
| **CloudTrail** | AWS's log of API calls (who did what, when) |
| **SigV4** | The method AWS uses to prove a request came from you, without sending your secret key |

---

# Part 1: What Is a Secret, and Why Is It Hard?

## 1.1 The house key analogy

Think of a house key.

- You must **keep it somewhere** so you can get in.
- If it sits under the doormat, **anyone** can get in.
- If you make 50 copies, you **can't track** who has one.
- If you change the lock, you must **hand out new keys** to everyone.

Secrets are the same. Four problems:

| Problem | Meaning |
|---|---|
| **Storage** | Where do I keep it? |
| **Distribution** | How does the app receive it? |
| **Access control** | Who may read it? |
| **Change** | How do I replace it without breaking things? |

## 1.2 What "good" looks like

| Goal | How |
|---|---|
| Stored in **one** place | A vault service |
| Encrypted | KMS |
| Only the right app can read it | IAM permissions |
| Every read is logged | CloudTrail |
| Easy to change | Rotation |
| App fetches it **when needed** | Runtime fetch, not baked in |

---

# Part 2: Bad Places to Keep Secrets

## 2.1 The list

| Where | Why it's bad |
|---|---|
| **Source code / Git** | Git history is permanent. Deleting the file later doesn't remove it from old commits |
| **AMI** | Copied into every instance. AMIs get shared. Can't change without a new image |
| **User data** | Anyone on the instance can read it from IMDS. Also visible in console/API |
| **Plaintext env vars** | Readable from `/proc/<pid>/environ`, shown by `docker inspect`, leaked in crash dumps |
| **Config file on disk** | Ends up in snapshots and backups. Any file-read bug exposes it |
| **Tags** | Visible to anyone who can describe the instance |
| **Chat / tickets / docs** | Copied and searchable forever |

## 2.2 Common root cause

The secret is **static** (never changes) and **copied** (lives in many places).

## 2.3 Try it: see the problems yourself (5 min)

On any EC2 instance:

**Demo A: user data is readable**
```bash
TOKEN=$(curl -s -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
curl -s -H "X-aws-ec2-metadata-token: $TOKEN" \
  http://169.254.169.254/latest/user-data
```
If you had put a password in user data, you just read it with no special permission.

**Demo B: env vars are readable**
```bash
export DB_PASSWORD="supersecret123"
sleep 600 &
cat /proc/$!/environ | tr '\0' '\n' | grep DB_PASSWORD
```
Anyone with access to that user (or root) can read it the same way.

**Write down:** which two other places on the list above could you demo?

---

# Part 3: The Big Idea: Fetch at Runtime

## 3.1 The flow

```
App starts
   │
   ▼
Asks the vault: "give me the DB password"
   │
   ▼
Vault checks: "who are you? are you allowed?"
   │
   ▼
Vault returns the secret (encrypted in transit)
   │
   ▼
App keeps it in memory only
```

## 3.2 The "secret zero" problem

> If the app must log in to the vault, what password does it use to log in?

A password for the vault just moves the problem.

## 3.3 The answer: the instance role

| Without role | With role |
|---|---|
| App needs a stored credential | App stores **nothing** |
| Credential must be protected | Identity comes from the **EC2 platform** |
| Hard to rotate | Credentials are temporary and auto-rotated |

**Trust chain:**
```
EC2 platform → IMDS → temporary role credentials → vault → secret
```

Nothing secret was ever written down to start. This is the central idea of the course.

**Link to your IMDS lesson:** if IMDSv1 is on and your app has an SSRF bug, the attacker can steal the role credentials and then read your secrets. Enforcing IMDSv2 protects the first link of this chain.

---

# Part 4: Building Blocks (Quick Recap)

## 4.1 Role and instance profile

A role has two policies:

| Policy | Question it answers |
|---|---|
| **Trust policy** | *Who* may become this role? (here: the EC2 service) |
| **Permission policy** | *What* may the role do? |

Trust policy for EC2:
```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Principal": { "Service": "ec2.amazonaws.com" },
    "Action": "sts:AssumeRole"
  }]
}
```

The role is attached to the instance through an **instance profile**. (The console creates the instance profile for you when you make the role.)

## 4.2 How your code gets credentials

```
SDK/CLI looks in order:
  1. Environment variables
  2. Config files (~/.aws)
  3. IMDS (the instance role)   ← what we use
```
That's why `aws s3 ls` works on an instance with a role and you never typed a key.

## 4.3 KMS in one page

KMS holds keys that **encrypt your data**. Both vault services use it.

**Envelope encryption (simple version):**
```
1. Vault asks KMS: "give me a one-time data key"
2. Vault encrypts your secret with that data key
3. Vault stores: [encrypted secret] + [encrypted copy of data key]
4. To read: vault asks KMS to decrypt the data key, then decrypts the secret
```

Why? Big data stays out of KMS. KMS only handles tiny keys, and every use is logged.

**Two kinds of key:**

| | AWS managed (`aws/secretsmanager`) | Customer managed (CMK) |
|---|---|---|
| Created by | AWS | You |
| Cost | Free | About $1/month per key |
| Key policy | Fixed by AWS | You control |
| Cross-account sharing | **No** | Yes |
| Best for | Simple cases | Control, auditing, sharing |

**Rule to remember:** reading an encrypted secret needs permission on **the secret** and permission on **the key**. (Part 7.)

---

# Part 5: SSM Parameter Store

## 5.1 In one line
A hierarchical key-value store for configuration, which can also hold encrypted secrets.

## 5.2 Parameter types

| Type | Stored as | Use for |
|---|---|---|
| `String` | Plain text | Hostnames, flags, non-sensitive config |
| `StringList` | Comma-separated | Lists |
| `SecureString` | Encrypted with KMS | Passwords, API keys |

## 5.3 Tiers

| | Standard | Advanced |
|---|---|---|
| Max value size | 4 KB | 8 KB |
| Count limit | 10,000 | 100,000 |
| Cost | Free | Charged per parameter |
| Policies (e.g. expiry) | No | Yes |

## 5.4 Hierarchy is the superpower

```
/prod/shop/db/host
/prod/shop/db/password
/prod/shop/api/stripe-key
/dev/shop/db/password
```

You can grant access to a whole branch: `/prod/shop/*`. Different environments and apps stay separate by name.

## 5.5 Commands

```bash
# Create
aws ssm put-parameter --name "/lab/app/api-key" \
  --value "abc123" --type SecureString

# Read (decrypted)
aws ssm get-parameter --name "/lab/app/api-key" --with-decryption

# Read only the value
aws ssm get-parameter --name "/lab/app/api-key" --with-decryption \
  --query Parameter.Value --output text

# Read a whole branch
aws ssm get-parameters-by-path --path "/lab/app" --recursive --with-decryption

# Update
aws ssm put-parameter --name "/lab/app/api-key" \
  --value "newvalue" --type SecureString --overwrite

# History (versions)
aws ssm get-parameter-history --name "/lab/app/api-key"
```

Without `--with-decryption` you get the **encrypted blob**, not the value.

## 5.6 Permissions for the role

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": [
      "ssm:GetParameter",
      "ssm:GetParameters",
      "ssm:GetParametersByPath"
    ],
    "Resource": [
      "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/lab/app",
      "arn:aws:ssm:REGION:ACCOUNT_ID:parameter/lab/app/*"
    ]
  }]
}
```
If the parameter uses a **customer managed key**, the role also needs `kms:Decrypt` on that key. With the default `aws/ssm` key, no extra KMS permission is normally needed.

## 5.7 Limits to know
- No built-in rotation (you build it yourself)
- Fewer sharing features than Secrets Manager
- Great value: standard tier is free

---

# Part 6: Secrets Manager

## 6.1 In one line
A service built only for secrets, with encryption, versioning, **automatic rotation**, replication and fine-grained access control.

## 6.2 Key facts

| Fact | Value |
|---|---|
| Max secret size | 64 KB |
| Encrypted with | KMS (`aws/secretsmanager` by default, or your CMK) |
| Cost | About $0.40 per secret per month plus about $0.05 per 10,000 API calls (check current pricing) |
| Deletion | Has a **recovery window** of 7 to 30 days (default 30) |
| Format | Plain text or JSON (JSON is common: `{"username":"...","password":"..."}`) |

## 6.3 Commands

```bash
# Create
aws secretsmanager create-secret --name lab/db \
  --secret-string '{"username":"admin","password":"Pass#1"}'

# Read
aws secretsmanager get-secret-value --secret-id lab/db

# Read only the secret text
aws secretsmanager get-secret-value --secret-id lab/db \
  --query SecretString --output text

# Add a new version
aws secretsmanager put-secret-value --secret-id lab/db \
  --secret-string '{"username":"admin","password":"Pass#2"}'

# See versions and labels
aws secretsmanager list-secret-version-ids --secret-id lab/db

# Delete (with recovery window)
aws secretsmanager delete-secret --secret-id lab/db \
  --recovery-window-in-days 7

# Undo a delete
aws secretsmanager restore-secret --secret-id lab/db
```

## 6.4 Versions and staging labels

Every time the secret changes, a **new version** is created. Labels say which is which.

| Label | Meaning |
|---|---|
| `AWSCURRENT` | What apps get by default |
| `AWSPENDING` | A new version being prepared (used during rotation) |
| `AWSPREVIOUS` | The last current version |

Picture:
```
Version A  [AWSPREVIOUS]
Version B  [AWSCURRENT]   ← get-secret-value returns this
Version C  [AWSPENDING]   ← being tested, not yet live
```
Moving the `AWSCURRENT` label is how a new secret goes live. That is why rotation is safe: the label only moves after the new value is proven to work.

**Rollback** = move the label back:
```bash
aws secretsmanager update-secret-version-stage --secret-id lab/db \
  --version-stage AWSCURRENT \
  --move-to-version-id <OLD_VERSION_ID> \
  --remove-from-version-id <BAD_VERSION_ID>
```

## 6.5 Parameter Store vs Secrets Manager

| Question | Parameter Store | Secrets Manager |
|---|---|---|
| Built-in rotation? | No | **Yes** |
| Cost | Free (standard) | Per secret per month |
| Cross-account sharing | Hard | **Resource policy** |
| Multi-region replication | No | **Yes** |
| Hierarchy / paths | **Strong** | Names with `/` |
| Best for | Config, simple secrets | Passwords and keys that rotate |

**Quick rule:**
- Needs rotation or sharing → Secrets Manager
- Sensitive config that rarely changes → Parameter Store

## 6.6 Deletion gotcha
A secret scheduled for deletion **cannot be read**. You get an `InvalidRequestException`. Restore it first. You can also force immediate deletion (no recovery), so be careful with that permission.

---

# Part 7: Permissions: The Two Locks

## 7.1 The main idea

An encrypted secret is protected by **two separate locks**.

```
Request ──► LOCK 1: IAM / secret policy ──► LOCK 2: KMS key ──► Secret returned
                 must allow                      must allow
```

| Lock | Checked by | Needed permission |
|---|---|---|
| Lock 1 | Secrets Manager (IAM + secret's resource policy) | `secretsmanager:GetSecretValue` |
| Lock 2 | KMS (key policy + IAM) | `kms:Decrypt` |

**If either fails, you get `AccessDeniedException`.**

> **Debugging habit:** the error message names the missing permission. Read it. If it says `kms:Decrypt`, the problem is Lock 2.

## 7.2 Least-privilege policy for Secrets Manager

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": "secretsmanager:GetSecretValue",
    "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:prod/shop/db-??????"
  }]
}
```

| Part | Why |
|---|---|
| Action = only `GetSecretValue` | App must not list, change or delete secrets |
| Resource = exact secret | App sees only its own secret |
| `-??????` | AWS adds a 6-character random suffix to every ARN |

**Wildcard trap:** `prod/shop/db-*` would also match `prod/shop/db-backup-AbCdEf`. Use `-??????` for an exact match.

## 7.3 Adding the KMS lock (for a customer managed key)

Add to the role's policy:
```json
{
  "Effect": "Allow",
  "Action": "kms:Decrypt",
  "Resource": "arn:aws:kms:REGION:ACCOUNT_ID:key/KEY_ID",
  "Condition": {
    "StringEquals": {
      "kms:ViaService": "secretsmanager.REGION.amazonaws.com"
    }
  }
}
```
`kms:ViaService` means "this key may only be used when the request comes through Secrets Manager", not directly.

## 7.4 One role per app

| Design | Result if one app is hacked |
|---|---|
| One shared role for all apps | **Every** secret is exposed |
| One role per app | Only **that app's** secrets are exposed |

This is called limiting the **blast radius**.

## 7.5 Resource policy (the secret's own rules)

A policy attached to the secret. It can:
- Allow another AWS account to read it (needs a CMK)
- Deny access unless the request comes from a specific VPC endpoint

```json
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Deny",
    "Principal": "*",
    "Action": "secretsmanager:GetSecretValue",
    "Resource": "*",
    "Condition": {
      "StringNotEquals": { "aws:SourceVpce": "vpce-0abc1234567890def" }
    }
  }]
}
```
Warning: this also blocks you from the console and from your laptop. Test carefully, and keep an admin path.

## 7.6 Tag-based access (advanced, scales well)

Instead of listing every secret, match tags:

- Secret tag: `app = shop`
- Role tag: `app = shop`

```json
{
  "Effect": "Allow",
  "Action": "secretsmanager:GetSecretValue",
  "Resource": "*",
  "Condition": {
    "StringEquals": {
      "secretsmanager:ResourceTag/app": "${aws:PrincipalTag/app}"
    }
  }
}
```
New secrets with the right tag work automatically.

---

# Part 8: Rotation (Deep Dive)

## 8.1 Why rotate?

| Without rotation | With rotation |
|---|---|
| A leaked secret works **forever** | A leaked secret works only until the next rotation |
| Ex-employees may still know it | Old values go dead |
| Changing it is a risky manual job | Changing it is automated and routine |

## 8.2 How Secrets Manager rotates

A **Lambda function** runs four steps:

| Step | Name | What it does |
|---|---|---|
| 1 | `createSecret` | Generates a new password and stores it as `AWSPENDING` |
| 2 | `setSecret` | Changes the password **in the real database** |
| 3 | `testSecret` | Logs in with the new password to prove it works |
| 4 | `finishSecret` | Moves `AWSCURRENT` to the new version |

Timeline:
```
Before:  v1 [AWSCURRENT]
Step 1:  v1 [AWSCURRENT]   v2 [AWSPENDING]
Step 2:  DB password now = v2's password
Step 3:  test login with v2 → OK
Step 4:  v1 [AWSPREVIOUS]  v2 [AWSCURRENT]
```
Apps reading `AWSCURRENT` see the old secret until step 4, so they never see a broken half-state.

For RDS, AWS gives ready-made rotation Lambda templates. You pick a schedule (for example every 30 days) and Secrets Manager does the rest. For other systems you write a custom Lambda using the same four steps.

The rotation Lambda needs network access to **both** the database and the Secrets Manager endpoint (usually put it in the VPC with a VPC endpoint).

## 8.3 The trap: apps holding old passwords

```
Day 1:  App starts, fetches password P1, keeps it in memory
Day 30: Rotation changes DB password to P2
Day 30: App opens a new DB connection with P1  →  FAILS
```

### Fix 1: Re-fetch on failure

```
try connect with cached secret
if auth fails:
    clear cache
    fetch secret again
    retry once
```

### Fix 2: Alternating users strategy

```
Two DB users: app_A and app_B (same permissions)

Rotation 1: change app_B's password → make it AWSCURRENT
            (app_A still works with its old password)
Rotation 2: change app_A's password → make it AWSCURRENT
            (app_B still works)
```
The old credentials stay valid for a full cycle, so an app that cached them has time to refresh. This is also the better choice for large fleets.

### Which to use?

| Situation | Choice |
|---|---|
| Small app, short-lived connections | Single-user + retry on failure |
| Large fleet, long-lived connections, zero downtime needed | Alternating users |
| Best of all | Both |

## 8.4 Rotation for non-database secrets
API keys for third-party services: write a custom Lambda whose `setSecret` step calls the provider's "create new key" API, and `testSecret` makes a harmless call to prove the key works.

## 8.5 When rotation fails
Things to check:
- Lambda can't reach the DB (security group, subnet, route)
- Lambda can't reach Secrets Manager (no endpoint / NAT)
- Lambda's role lacks permission
- Secret is stuck with an `AWSPENDING` label from a previous failed run
- Check the Lambda's CloudWatch Logs first

## 8.6 Better than rotation: no password at all

**RDS IAM database authentication:**

```
1. App uses its role credentials to generate a token
     aws rds generate-db-auth-token --hostname HOST --port 3306 \
        --region REGION --username dbuser
2. App uses the token AS the DB password
3. Token is valid about 15 minutes (needed only to open the connection)
```

| Benefit | Detail |
|---|---|
| Nothing stored | No password to leak |
| Nothing to rotate | Tokens are short-lived |
| Access is IAM-controlled | Uses `rds-db:connect` permission |

Requires SSL, and has connection-rate limits, so it suits moderate-traffic apps best.

**Principle:** wherever the target supports role-based auth (S3, DynamoDB, SQS, RDS IAM auth), use the role and skip the secret.

---

# Part 9: Writing the Application Code

## 9.1 The rules

| Rule | Reason |
|---|---|
| Fetch at **startup**, keep in memory | Fast and cheap |
| Add a **cache with expiry** | Picks up rotation |
| **Retry on auth failure** | Handles rotation timing |
| **Never log** secrets | Logs get copied everywhere |
| **Don't write** secrets to disk | Disk ends up in snapshots |
| Fetch **only what you need** | Smaller blast radius |

## 9.2 Basic read (Python + boto3)

```python
import json
import boto3

client = boto3.client("secretsmanager", region_name="ap-south-1")

def get_secret(name):
    response = client.get_secret_value(SecretId=name)
    return json.loads(response["SecretString"])

creds = get_secret("lab/db")
print(creds["username"])    # never print the password!
```

## 9.3 With a simple cache

```python
import time, json, boto3

client = boto3.client("secretsmanager", region_name="ap-south-1")
_cache = {}
TTL_SECONDS = 300

def get_secret(name, force_refresh=False):
    now = time.time()
    hit = _cache.get(name)
    if hit and not force_refresh and now - hit["time"] < TTL_SECONDS:
        return hit["value"]
    value = json.loads(client.get_secret_value(SecretId=name)["SecretString"])
    _cache[name] = {"time": now, "value": value}
    return value
```

## 9.4 Retry on auth failure

```python
def connect_to_db():
    creds = get_secret("lab/db")
    try:
        return open_connection(creds)           # your DB library call
    except AuthenticationError:
        creds = get_secret("lab/db", force_refresh=True)
        return open_connection(creds)           # retry once
```

AWS also provides a **caching library** (`aws-secretsmanager-caching` for Python and equivalents for Java and others) that does the cache and refresh for you.

## 9.5 Handling errors

| Error | Likely cause |
|---|---|
| `AccessDeniedException` | Missing IAM or KMS permission (Part 7) |
| `ResourceNotFoundException` | Wrong name, or **wrong region** |
| `InvalidRequestException` | Secret is scheduled for deletion |
| `DecryptionFailure` | Can't use the KMS key (disabled, deleted, or no permission) |
| `ThrottlingException` | Too many calls: add caching |
| Timeout / no response | No network path (Part 10) |

## 9.6 If a tool needs the secret as a file or env var

Avoid it when possible. If forced:

| Approach | Notes |
|---|---|
| Start-up script fetches and exports to **that process only** | Still an env var; limit who can read the process |
| Write to **tmpfs** (`/dev/shm`) with mode `0400` | Lives in memory, not on disk; delete when done |
| Never put it in the **systemd unit file** in plaintext | Unit files are world-readable |

---

# Part 10: Network Path

## 10.1 Where the calls go

Secrets Manager, SSM and KMS are **public AWS endpoints**. An instance in a private subnet needs a route to them.

| Option | Pros | Cons |
|---|---|---|
| **NAT gateway** | Simple | Cost, traffic goes via internet path |
| **VPC interface endpoints** | Private, stays in AWS network, can be locked down | Cost per endpoint, some setup |

## 10.2 Endpoints for this course

| Service | Endpoint name |
|---|---|
| Secrets Manager | `com.amazonaws.REGION.secretsmanager` |
| KMS | `com.amazonaws.REGION.kms` |
| SSM (Parameter Store) | `com.amazonaws.REGION.ssm` |

Setup checklist:
1. Create the interface endpoint in your VPC subnets
2. Turn on **Private DNS** (so the normal service name resolves to the private IP)
3. Security group on the endpoint allows **inbound 443** from your instances
4. Optional: add an **endpoint policy** restricting which secrets can be read through it

## 10.3 Troubleshooting a timeout

```
1. Does the subnet have a route to NAT or an endpoint?
2. Does the endpoint's security group allow 443 from the instance?
3. Is Private DNS enabled?
4. Does `nslookup secretsmanager.REGION.amazonaws.com` return a private IP?
```

---

# Part 11: Auditing and Detection

## 11.1 CloudTrail

Every API call is logged with: who (role and instance), when, from where, what.

Events to look for:

| Event name | Source | Meaning |
|---|---|---|
| `GetSecretValue` | secretsmanager | A secret was read |
| `GetParameter` / `GetParametersByPath` | ssm | A parameter was read |
| `Decrypt` | kms | A key was used |
| `PutSecretValue`, `UpdateSecret` | secretsmanager | A secret changed |
| `DeleteSecret` | secretsmanager | Deletion started |
| `RotateSecret` | secretsmanager | Rotation started |

In the console: CloudTrail → Event history → filter by Event name. (Event history shows the last 90 days. Create a trail for longer storage.)

## 11.2 Useful alarms

| Condition | Why it matters |
|---|---|
| `GetSecretValue` by an unexpected principal | Possible theft |
| `DeleteSecret` or `ScheduleKeyDeletion` | Destruction or sabotage |
| Many `AccessDenied` on secrets | Someone is probing |
| Secret read from an unusual IP | Possible stolen credentials |

## 11.3 GuardDuty

Detects instance role credentials used **outside** the instance, for example the finding `UnauthorizedAccess:IAMUser/InstanceCredentialExfiltration.OutsideAWS`. This is exactly what IMDSv1 + SSRF would produce.

## 11.4 Limiting stolen-credential use

Stolen role credentials work from anywhere until they expire. You can add conditions so they only work from your own network, using these global condition keys:

- `aws:ec2InstanceSourceVPC`
- `aws:ec2InstanceSourcePrivateIPv4`

(These are compared with where the request actually came from. They take care to set up, so it's an optional challenge in Part 12.)

## 11.5 What this course does NOT protect you from

If an attacker has **code execution** on the instance, they can do exactly what your app does: call `GetSecretValue` with the role.

What you still gain:

| Gain | How |
|---|---|
| Small blast radius | Only that role's secrets are exposed |
| Detection | CloudTrail and GuardDuty |
| Fast response | Deny the role, rotate the secret |
| Short life | Stolen credentials expire |

---

# Part 12: Assignments / Labs

**Conventions**
- Replace `REGION` with your region and `ACCOUNT_ID` with your 12-digit account ID.
- Run **admin commands** from CloudShell or your laptop (an admin identity).
- Run **app commands** on the **EC2 instance**.
- Each lab has **Goal, Steps, Done when**. Don't move on until "Done when" is true.

Get your account ID anytime:
```bash
aws sts get-caller-identity --query Account --output text
```

---

## Assignment 0: Prepare the lab instance (30 min)

**Goal:** an instance with a role that can do nothing yet.

**Steps**
1. Create an IAM role `lab-secrets-role`:
   - Trusted entity: AWS service → EC2
   - Attach **no** permissions for now
2. Launch a `t3.micro` (or free-tier type) Amazon Linux instance:
   - IAM instance profile: `lab-secrets-role`
   - **Metadata version: V2 only (token required)**
   - No SSH key pair needed if you use EC2 Instance Connect from the console
3. Connect to it (EC2 Instance Connect from the console is fine).
4. Confirm the role is working:
   ```bash
   aws sts get-caller-identity
   ```

**Done when:** the output shows `assumed-role/lab-secrets-role/i-...`.

**Think:** which IP address did the CLI get its credentials from, and which of the two IMDS versions did it use?

---

## Assignment 1: See the bad places (20 min)

**Goal:** prove to yourself why these places are unsafe.

**Steps**
1. Run Demo A and Demo B from Part 2.3.
2. In the console, open the instance → **Actions → Instance settings → Edit user data**. Note that anyone with that permission can read it.
3. Create a **tag** with a fake password on the instance. Run `aws ec2 describe-instances` from your admin identity and find it.

**Done when:** you have personally read a "secret" from user data, `/proc` and a tag.

**Write:** one sentence explaining why each is dangerous.

---

## Assignment 2: Parameter Store with least privilege (45 min)

**Goal:** instance can read **only** `/lab/app/*`.

**Steps (admin)**
1. Create two parameters:
   ```bash
   aws ssm put-parameter --name "/lab/app/api-key" --value "key-123" --type SecureString
   aws ssm put-parameter --name "/lab/other/api-key" --value "key-999" --type SecureString
   ```
2. Add an inline policy to `lab-secrets-role` (see Part 5.6) allowing only `/lab/app` and `/lab/app/*`.

**Steps (instance)**
3. Read the allowed one:
   ```bash
   aws ssm get-parameter --name "/lab/app/api-key" --with-decryption
   ```
4. Try the other one:
   ```bash
   aws ssm get-parameter --name "/lab/other/api-key" --with-decryption
   ```
5. Run the same command **without** `--with-decryption` and look at the value.
6. Run `get-parameters-by-path --path /lab --recursive` and see what happens.

**Done when:**
- Step 3 works
- Step 4 gives `AccessDeniedException`
- You can explain what you saw in steps 5 and 6

**Think:** why did step 6 behave that way?

---

## Assignment 3: Secrets Manager with exact-ARN policy (45 min)

**Goal:** instance reads `lab/db` but nothing else.

**Steps (admin)**
1. Create two secrets:
   ```bash
   aws secretsmanager create-secret --name lab/db \
     --secret-string '{"username":"admin","password":"Pass#1"}'
   aws secretsmanager create-secret --name lab/db-backup \
     --secret-string '{"username":"backup","password":"Backup#1"}'
   aws secretsmanager create-secret --name lab/other \
     --secret-string '{"token":"xyz"}'
   ```
2. Copy the ARN of `lab/db` (it ends in 6 random characters).
3. Attach this policy to the role, first using the **bad wildcard** `lab/db-*`:
   ```json
   {
     "Version": "2012-10-17",
     "Statement": [{
       "Effect": "Allow",
       "Action": "secretsmanager:GetSecretValue",
       "Resource": "arn:aws:secretsmanager:REGION:ACCOUNT_ID:secret:lab/db-*"
     }]
   }
   ```

**Steps (instance)**
4. Try all three secrets. Notice that `lab/db-backup` **also works**.
5. Change the Resource to `...:secret:lab/db-??????`.
6. Try all three again.

**Done when:** after step 6 only `lab/db` works.

**Think:** what real-world mistake does step 4 demonstrate?

---

## Assignment 4: The two locks with a CMK (60 min)

**Goal:** feel the IAM lock and the KMS lock separately.

**Steps (admin)**
1. Create a KMS key (console → KMS → Customer managed keys → Create):
   - Symmetric, Encrypt and decrypt
   - Alias `lab-key`
   - Leave the default key policy (it lets IAM policies control access)
2. Create a secret using that key:
   ```bash
   aws secretsmanager create-secret --name lab/cmk-secret \
     --kms-key-id alias/lab-key \
     --secret-string '{"api":"cmk-protected"}'
   ```
3. Give the role `GetSecretValue` on `lab/cmk-secret-??????` **only** (no KMS permission).

**Steps (instance)**
4. Read it:
   ```bash
   aws secretsmanager get-secret-value --secret-id lab/cmk-secret
   ```
   Read the error carefully. Which action is missing?

**Steps (admin)**
5. Add `kms:Decrypt` on that key's ARN (Part 7.3) to the role.

**Steps (instance)**
6. Read again. It should work.
7. **Bonus:** add the `kms:ViaService` condition, then try to decrypt directly with KMS from the instance (`aws kms decrypt ...`) and see it fail.

**Done when:** you saw it fail for `kms:Decrypt`, then succeed after adding it.

**Think:** which lock was failing in step 4: IAM or KMS?

---

## Assignment 5: Versions, labels and rollback (45 min)

**Goal:** understand staging labels by manipulating them.

**Steps (admin)**
1. Add a new version of `lab/db`:
   ```bash
   aws secretsmanager put-secret-value --secret-id lab/db \
     --secret-string '{"username":"admin","password":"Pass#2"}'
   ```
2. Show the versions:
   ```bash
   aws secretsmanager list-secret-version-ids --secret-id lab/db
   ```
   Write down which version ID has `AWSCURRENT` and which has `AWSPREVIOUS`.
3. Read each version:
   ```bash
   aws secretsmanager get-secret-value --secret-id lab/db --version-stage AWSPREVIOUS
   ```
4. **Roll back**: move `AWSCURRENT` to the old version using `update-secret-version-stage` (Part 6.4).
5. Fetch the default value again.

**Done when:** `get-secret-value` returns `Pass#1` again, and you can explain what happened to the labels.

**Think:** why is this safer than simply overwriting the password?

---

## Assignment 6: Application with cache and retry (60 min)

**Goal:** a small program that survives a secret change.

**Steps (instance)**
1. Install boto3: `pip3 install boto3` (or use the preinstalled one).
2. Create `app.py` using the cache from Part 9.3, with `TTL_SECONDS = 20` for the lab.
3. Make it loop every 5 seconds, printing:
   - the **username**
   - the **length** of the password (never the password itself)
   - whether the value came from the cache or a fresh call
4. While it runs, from admin run `put-secret-value` with a new password.
5. Watch how long until the program sees the new value.

**Extra:** add a fake `AuthenticationError` that triggers `force_refresh=True` when the password length changes, simulating a failed login.

**Done when:** you observed old value → cache expiry → new value, and can explain the delay.

**Think:** what's the trade-off in choosing TTL = 20 vs TTL = 3600?

---

## Assignment 7: Simulate rotation by hand (45 min)

**Goal:** act as the rotation Lambda.

**Steps (admin)** (using `lab/db`)
1. **createSecret:** make a new version labelled `AWSPENDING`:
   ```bash
   aws secretsmanager put-secret-value --secret-id lab/db \
     --secret-string '{"username":"admin","password":"Pass#3"}' \
     --version-stages AWSPENDING
   ```
2. **setSecret / testSecret:** pretend you changed and tested the DB password. Fetch the pending version to confirm it exists:
   ```bash
   aws secretsmanager get-secret-value --secret-id lab/db --version-stage AWSPENDING
   ```
3. Confirm the default read still returns the **old** value.
4. **finishSecret:** move `AWSCURRENT` to the pending version:
   ```bash
   aws secretsmanager update-secret-version-stage --secret-id lab/db \
     --version-stage AWSCURRENT \
     --move-to-version-id <PENDING_ID> \
     --remove-from-version-id <CURRENT_ID>
   ```
5. List versions and look at the labels.

**Done when:** you can draw the label timeline from Part 8.2 from memory.

**Optional (needs an RDS instance, costs money):** create a small RDS MySQL, store its credentials in Secrets Manager with the RDS secret type, enable rotation with the AWS template, and watch CloudWatch Logs for the Lambda's four steps.

---

## Assignment 8: Audit your own activity (30 min)

**Goal:** see what a defender sees.

**Steps**
1. Wait about 15 minutes after your previous labs.
2. CloudTrail → Event history → filter **Event source = secretsmanager.amazonaws.com**.
3. Find a `GetSecretValue` event that was **denied** (Assignment 3 or 4). Open it and read `errorCode` and `errorMessage`.
4. Find a successful one. Identify: the role, the instance ID, the source IP, the user agent.
5. Filter **Event source = kms.amazonaws.com** and find your `Decrypt` events. Find the **encryption context**.

**Done when:** you can answer: "Who read `lab/cmk-secret`, when, and from where?"

---

## Assignment 9 (Challenge): Make stolen credentials less useful

**Goal:** understand how a stolen role credential is limited.

**Steps**
1. On the instance (with IMDSv2) fetch the role credentials and copy them.
2. On your laptop or CloudShell, set them as environment variables (`AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`) and run `aws secretsmanager get-secret-value --secret-id lab/db`. It works from **outside** the instance. That is the risk.
3. Research `aws:ec2InstanceSourceVPC`, `aws:ec2InstanceSourcePrivateIPv4` and `aws:SourceVpc`.
4. Write a policy idea (on paper is fine) that denies the role's credentials when used from outside your VPC.

**Hint:** `aws:SourceVpc` is only filled in when requests travel through a **VPC endpoint**, so the pattern pairs the endpoint (Part 10) with a deny condition.

**Done when:** you can explain why the stolen credentials worked in step 2 and what extra check would stop them.

> Delete or let those temporary credentials expire after this test.

---

## Assignment 10 (Capstone): Design review (60 min, on paper)

**Scenario:** a company runs three workloads on EC2 in private subnets:

| App | Needs |
|---|---|
| **Shop web app** | MySQL password that must rotate every 30 days, zero downtime |
| **Nightly report job** | A third-party payment-provider API key, rotated yearly by a human |
| **Frontend config** | Feature flags and service hostnames (not sensitive, but different for dev/prod) |

**Deliver a one-page design answering:**

1. Which service for each of the three (and why)?
2. How many IAM roles, and what does each role allow? (Write the policy for one.)
3. Which KMS key strategy (AWS managed vs CMK, one key or several)?
4. How does the shop app handle rotation without downtime?
5. What network setup lets private instances reach the services?
6. What do you log and alert on?
7. What happens if the shop app's instance is compromised? What is exposed and how do you respond?
8. Which of the three could avoid a stored secret entirely?

**Scoring guide**

| Points | Criterion |
|---|---|
| 2 | Correct service choice for each app |
| 2 | One role per app with exact-ARN least privilege |
| 2 | Correct two-lock KMS reasoning |
| 2 | Concrete rotation plan (alternating users and/or retry) |
| 1 | Network endpoints named |
| 1 | Detection and incident-response plan |
| **10** | **Total** |

---

# Part 13: Quiz

Answer without looking back first.

**Concept**
1. Name four places a secret should never be stored, and one reason for each.
2. What is the "secret zero" problem?
3. How does the instance role solve it?

**Services**
4. Give two reasons to pick Secrets Manager over Parameter Store.
5. Give one reason to pick Parameter Store over Secrets Manager.
6. What do `AWSCURRENT`, `AWSPENDING` and `AWSPREVIOUS` mean?

**Permissions**
7. An app's IAM policy allows `GetSecretValue` on the right secret, yet it gets `AccessDeniedException`. What do you check first?
8. Why is `...:secret:prod/db-*` risky and what's the better pattern?
9. Why one role per application?
10. What does `kms:ViaService` do?

**Rotation**
11. List the four rotation steps in order.
12. Why does a long-running app fail after rotation? Give two fixes.
13. When does a secret **not** need to exist at all? Give an example.

**Operations**
14. A private-subnet instance times out calling Secrets Manager. List three things to check.
15. Which CloudTrail events tell you who read a secret?
16. If an attacker gets code execution on the instance, what has the vault design still given you?

**Scenario**
17. A developer put the DB password in user data "just temporarily". List every way it could be read and the steps to fix it properly.
18. Your secret has been scheduled for deletion by mistake. What do you do, and by when?

---

# Part 14: Cleanup (Do This!)

Run from admin:

```bash
# Secrets (force delete for lab; in real life keep the recovery window)
for s in lab/db lab/db-backup lab/other lab/cmk-secret; do
  aws secretsmanager delete-secret --secret-id $s --force-delete-without-recovery
done

# Parameters
aws ssm delete-parameter --name /lab/app/api-key
aws ssm delete-parameter --name /lab/other/api-key
```

Then:
- Terminate the EC2 instance
- Delete the role `lab-secrets-role` and its instance profile
- KMS: schedule deletion of `lab-key` (minimum waiting period is 7 days; the key costs money until then, and cancelling is possible during the wait)
- Delete any VPC endpoints or RDS instance you created
- Check **Billing → Bills** tomorrow to make sure nothing is running

---

# Part 15: Cheat Sheet

## Decision table

| I need to... | Use |
|---|---|
| Store config values | Parameter Store (`String`) |
| Store a password that doesn't rotate | Parameter Store (`SecureString`) |
| Store a password that rotates | Secrets Manager |
| Share a secret across accounts | Secrets Manager + CMK + resource policy |
| Avoid a password completely | IAM auth (RDS), role-based access |
| Find who read a secret | CloudTrail |

## Permissions checklist (app can't read the secret)

```
□ Right region?
□ Right secret name?
□ Role attached to the instance?
□ Role allows GetSecretValue on that exact ARN?
□ Role allows kms:Decrypt on the key (if CMK)?
□ Key policy allows the role (or delegates to IAM)?
□ Secret resource policy not denying?
□ Any SCP or permission boundary blocking?
□ Secret not scheduled for deletion?
□ Network path (endpoint/NAT, DNS, security group 443)?
```

## Golden rules

1. Never store secrets in code, AMIs, user data, env vars, files or tags.
2. Use the **instance role** as the starting identity.
3. **One role per app**, exact ARN, only `GetSecretValue`.
4. Remember the **two locks**: IAM and KMS.
5. **Cache** and **retry** in the app.
6. **Rotate**, and design for it.
7. Prefer **no secret** (IAM auth) when possible.
8. **Log and alert** on secret access.
9. Enforce **IMDSv2** so the role can't be stolen easily.

---

# Part 16: Answer Key

## Quiz answers

1. Any four of: Git (history is permanent), AMI (copied everywhere), user data (readable via IMDS), plaintext env vars (`/proc`), config files (snapshots/backups), tags (visible to describers).
2. The app needs a credential to log in to the vault, so you've just moved the problem.
3. The platform vends temporary credentials through IMDS, so the app stores nothing; identity comes from the EC2 role.
4. Any two of: built-in rotation, cross-account sharing, multi-region replication, versioned staging labels.
5. It's free at the standard tier and has strong hierarchy for configuration.
6. `AWSCURRENT` = live version apps read; `AWSPENDING` = new version being prepared; `AWSPREVIOUS` = the last live version.
7. The KMS side: does the role have `kms:Decrypt` on the key, and does the key policy allow it? Also check the error message text and region.
8. It also matches `prod/db-backup-xxxxxx`. Use `-??????` to match exactly the 6-character suffix.
9. Limits blast radius: a compromise of one app exposes only that app's secrets.
10. Restricts the key so it can only be used when the call comes through a specified AWS service.
11. `createSecret` → `setSecret` → `testSecret` → `finishSecret`.
12. It holds the old password in memory after the DB password changed. Fixes: re-fetch and retry on auth failure; alternating-users rotation (also short cache TTL).
13. When the target supports role-based auth, e.g. RDS IAM authentication, or S3/DynamoDB access via the instance role.
14. Route to NAT or endpoint; endpoint security group allows 443; Private DNS enabled (also: role permissions, correct region).
15. `GetSecretValue` (secretsmanager) and `Decrypt` (kms), plus `GetParameter` for Parameter Store.
16. Small blast radius, audit trail, ability to revoke and rotate quickly, and credentials that expire.
17. User data can be read from IMDS (by anything on the instance, including via SSRF), through the console/API (`DescribeInstanceAttribute`), and it persists in the launch template/instance. Fix: remove it from user data, put the secret in Secrets Manager/Parameter Store, have the app fetch it with its role, **rotate the password** (it should be considered exposed), enforce IMDSv2, and check CloudTrail for who read it.
18. Restore it with `restore-secret` before the recovery window ends (7 to 30 days, default 30). After that it's gone permanently.

## Assignment hints

| Assignment | Hint / expected result |
|---|---|
| 0 | Output contains `assumed-role/lab-secrets-role` |
| 1 | The tag, user data and `/proc` all expose the value in plain text |
| 2, step 5 | Without `--with-decryption` you see an encrypted blob. Step 6: you only get results under the allowed branch or an `AccessDenied` if the path policy doesn't cover `/lab` itself |
| 3, step 4 | `lab/db-backup` was readable because `lab/db-*` is a wildcard that includes it |
| 4, step 4 | The error names `kms:Decrypt`. That's the KMS lock, not the IAM lock |
| 5 | After rollback, the old version has `AWSCURRENT`; the bad one has no label or `AWSPREVIOUS` |
| 6 | New value appears after at most TTL seconds. Short TTL = faster pick-up but more API calls and cost |
| 7 | Default read returns old value until step 4, then new |
| 8 | Denied events show `errorCode: AccessDenied`; `Decrypt` events carry an encryption context with the secret's ARN |
| 9 | Stolen credentials work anywhere until restricted by source-VPC conditions or expiry |

## Capstone model answer (summary)

| Question | Model answer |
|---|---|
| 1 | Shop: **Secrets Manager** (rotation). Report job: **Secrets Manager** or `SecureString` (rotates rarely by human; Secrets Manager adds versioning and audit). Frontend config: **Parameter Store** `String`, paths `/dev/...` and `/prod/...` |
| 2 | **Three roles**, one per app. Shop role: `GetSecretValue` on `prod/shop/db-??????` + `kms:Decrypt` on its key. Report role: its API-key ARN only. Frontend role: `GetParametersByPath` on `/prod/frontend/*` |
| 3 | CMK per environment (or per sensitivity) for audit and separation; AWS managed key is acceptable for low-risk config |
| 4 | Alternating-users rotation + cache TTL + retry on auth failure; MySQL rotation Lambda in the VPC |
| 5 | Interface endpoints for Secrets Manager, KMS and SSM with Private DNS and a 443-allowing security group |
| 6 | CloudTrail alerts on unexpected `GetSecretValue`, `DeleteSecret`, `ScheduleKeyDeletion`; GuardDuty on; IMDSv2 enforced via Config rule |
| 7 | Exposed: only that app's secret(s). Response: deny the role (inline deny), rotate the secrets, isolate the instance, review CloudTrail |
| 8 | The shop DB could use **RDS IAM authentication**; the frontend needs no secrets; the third-party API key must stay a secret |

---

**End of course.** When you've completed the assignments and quiz, send me your capstone design or any quiz answers you're unsure about and I'll review them. Then we move on to the next topic: **SSM Session Manager instead of SSH**.
