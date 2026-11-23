# Terraform Test Cases

This document explains the 24 Terraform configurations inside `benchmark/cases/`. The dataset is divided into four common cloud security categories:

1. **Public Cloud Storage (`ST`)**
2. **Encryption at Rest (`EN`)**
3. **Identity and Permissions (`ID`)**
4. **Network Exposure (`NW`)**

For every vulnerability case, there are two files:
- **`<ID>-vulnerable.tf`**: Contains a specific security misconfiguration that the scanners should flag.
- **`<ID>-fixed.tf`**: Fixes that exact misconfiguration so we can verify whether the scanners stop raising the alarm (or if they produce a false alarm).

In addition, there are four **benign control cases (`BC-01.tf` to `BC-04.tf`)** - one per category - representing safe baseline configurations that should not trigger any targeted security alerts.

---

## 1. Public Cloud Storage (`ST-01` to `ST-03`)

Amazon S3 buckets are private by default, but they can accidentally be exposed to the internet in three different ways: through legacy Access Control Lists (ACLs), disabled public-access blocks, or overly permissive bucket policies.

### `ST-01`: Public S3 Bucket via ACL
- **Vulnerable (`ST-01-vulnerable.tf`)**: Creates an S3 bucket (`aws_s3_bucket`) and attaches an `aws_s3_bucket_acl` resource with `acl = "public-read"`. This allows anyone on the internet to list and read files in the bucket.
- **Fixed (`ST-01-fixed.tf`)**: Removes the public ACL and attaches an `aws_s3_bucket_public_access_block` with all four protection settings set to `true`.
- **What we test**: Whether the tools detect legacy ACL exposure (`CKV_AWS_20` in Checkov, query `38c5ee0d` in KICS) and missing public-access block protections (`CKV2_AWS_6`).

### `ST-02`: Disabled S3 Public-Access Block
- **Vulnerable (`ST-02-vulnerable.tf`)**: Defines an `aws_s3_bucket_public_access_block` resource where all four safety flags (`block_public_acls`, `block_public_policy`, `ignore_public_acls`, `restrict_public_buckets`) are explicitly set to `false`. Even if the bucket is not immediately public, disabling these guardrails allows future policies or ACLs to leak data.
- **Fixed (`ST-02-fixed.tf`)**: Changes all four public-access block flags to `true`.
- **What we test**: Whether the tools check the individual boolean flags inside the public-access block (`CKV_AWS_53` to `56` and `CKV2_AWS_6` in Checkov, and queries `1a4bc881`, `4fa66806`, `d0cc8694` in KICS).

### `ST-03`: Public S3 Bucket Policy (`Principal = "*"`)
- **Vulnerable (`ST-03-vulnerable.tf`)**: Attaches an `aws_s3_bucket_policy` that grants `s3:GetObject` (read/download files) to `Principal = "*"` (everyone on the internet).
- **Fixed (`ST-03-fixed.tf`)**: Removes the public policy and enforces the bucket public-access block.
- **What we test**: Whether the tools parse the JSON policy inside the Terraform resource and recognize that `Principal = "*"` exposes the bucket (`CKV_AWS_70` and `CKV2_AWS_6` in Checkov, and queries `7af43613` and `1df37f4b` in KICS).

---

## 2. Encryption at Rest (`EN-01` to `EN-02`)

Cloud storage and disk volumes should be encrypted at rest so that underlying data cannot be read if physical media, snapshots, or backups are exposed.

### `EN-01`: Missing S3 Server-Side Encryption
- **Vulnerable (`EN-01-vulnerable.tf`)**: Creates an `aws_s3_bucket` without attaching an `aws_s3_bucket_server_side_encryption_configuration` resource.
- **Fixed (`EN-01-fixed.tf`)**: Attaches an `aws_s3_bucket_server_side_encryption_configuration` resource configured with standard `sse_algorithm = "AES256"` encryption.
- **What we test**: In modern AWS Terraform templates, S3 encryption is configured in a separate companion resource rather than inside the bucket block itself.
  - On the vulnerable file, Checkov flags the bucket via `CKV_AWS_145` (which requires explicit KMS encryption `aws:kms` on every S3 bucket), whereas **KICS misses it (False Negative)** when the encryption companion resource is omitted.
  - On the fixed file, **Checkov raises a False Positive** because the same rule (`CKV_AWS_145`) requires KMS encryption (`aws:kms`) and does not distinguish between an unencrypted bucket and one encrypted with standard `AES256`.

### `EN-02`: Unencrypted EBS Disk Volume
- **Vulnerable (`EN-02-vulnerable.tf`)**: Creates an `aws_ebs_volume` (a virtual hard drive for EC2 servers) with `encrypted = false`.
- **Fixed (`EN-02-fixed.tf`)**: Sets `encrypted = true` on the EBS volume.
- **What we test**: Basic attribute checking on block storage resources (`CKV_AWS_3` in Checkov, query `cc997676` in KICS). Both tools detect the vulnerability and mark the fix as clean.

---

## 3. Identity and Permissions (`ID-01` to `ID-02`)

Following the principle of least privilege, IAM policies should only grant the specific actions and resources needed for a task.

### `ID-01`: Wildcard Administrative IAM Policy (`Action = "*"`, `Resource = "*"`)
- **Vulnerable (`ID-01-vulnerable.tf`)**: Defines an `aws_iam_policy` with `Effect = "Allow"`, `Action = "*"`, and `Resource = "*"`. Any user or service given this policy gets full administrator control over the entire AWS account.
- **Fixed (`ID-01-fixed.tf`)**: Restricts `Action` to a single read operation (`s3:GetObject`) and scopes `Resource` to a single private bucket ARN.
- **What we test**: Whether the tools parse inline JSON policies to catch wildcard admin privileges (9 rules in Checkov: `CKV_AWS_62`, `63`, `286` to `290`, `355`, and `CKV2_AWS_40`; 3 rules in KICS: `2f37c4a3`, `575a2155`, and `ba2ed23b`).

### `ID-02`: Unrestricted `iam:PassRole` Privilege Escalation
- **Vulnerable (`ID-02-vulnerable.tf`)**: Defines a standalone `aws_iam_policy` that grants `Action = "iam:PassRole"` on `Resource = "*"`. Even without full `*` actions, an attacker with unrestricted `iam:PassRole` can attach an existing administrator role to an EC2 instance or Lambda function they control and take over the account.
- **Fixed (`ID-02-fixed.tf`)**: Restricts `iam:PassRole` so it can only pass one specific application role ARN (`arn:aws:iam::123456789012:role/application-role`).
- **What we test**: Whether the tools detect `iam:PassRole` on a wildcard resource (`*`) inside a standalone `aws_iam_policy`. Checkov catches this through its permissions-management (`CKV_AWS_289`) and restrictable-wildcard-resource (`CKV_AWS_355`) checks, while **KICS misses it (False Negative)** because its PassRole queries only inspect inline role policies or attached identity policies rather than a standalone unattached `aws_iam_policy`.

---

## 4. Network Exposure (`NW-01` to `NW-03`)

AWS Security Groups act as virtual firewalls. Allowing incoming traffic from `0.0.0.0/0` (any IP address on the internet) on management or all ports exposes servers to automated scanning and brute-force attacks.

### `NW-01`: SSH (Port 22) Open to the Internet
- **Vulnerable (`NW-01-vulnerable.tf`)**: Configures an `aws_security_group` allowing TCP port `22` (Linux remote login via SSH) from `cidr_blocks = ["0.0.0.0/0"]`.
- **Fixed (`NW-01-fixed.tf`)**: Restricts SSH access to an internal private network range (`10.0.0.0/8`).
- **What we test**: Detection of public SSH exposure (`CKV_AWS_24` in Checkov; queries `65905cec`, `381c3f2a`, and `4728cd65` in KICS).

### `NW-02`: RDP (Port 3389) Open to the Internet
- **Vulnerable (`NW-02-vulnerable.tf`)**: Configures an `aws_security_group` allowing TCP port `3389` (Windows Remote Desktop) from `cidr_blocks = ["0.0.0.0/0"]`.
- **Fixed (`NW-02-fixed.tf`)**: Restricts RDP access to the private network range `10.0.0.0/8`.
- **What we test**: Detection of public RDP exposure (`CKV_AWS_25` in Checkov; queries `151187cb`, `381c3f2a`, and `4728cd65` in KICS).

### `NW-03`: All Ports and Protocols Open to the Internet
- **Vulnerable (`NW-03-vulnerable.tf`)**: Configures an `aws_security_group` with `from_port = 0`, `to_port = 0`, `protocol = "-1"` (all protocols and all ports), and `cidr_blocks = ["0.0.0.0/0"]`, disabling the firewall for incoming traffic.
- **Fixed (`NW-03-fixed.tf`)**: Restricts incoming traffic to TCP port `443` (HTTPS) from the private range `10.0.0.0/8`.
- **What we test**: Both tools detect the open firewall, but behave very differently: Checkov triggers 4 specific rules (`CKV_AWS_24`, `25`, `260`, and `277` for port `-1`), whereas KICS triggers 4 targeted rules (`151187cb`, `381c3f2a`, `4728cd65`, and `65905cec`) and tests the open range against every port in its sensitive-ports list one by one, producing 129 targeted findings (including 126 instances of query `381c3f2a`, and 137 total findings) for a single 10-line file.

---

## 5. Benign Control Cases (`BC-01` to `BC-04`)

These four files represent normal, properly configured resources (one for each category) used as control cases to verify that the tools do not raise false alarms on safe infrastructure:

- **`BC-01.tf` (Public Storage Control)**: A private S3 bucket with all public-access block settings enabled (`true`) and server-side encryption configured.
- **`BC-02.tf` (Encryption Control)**: A 20 GB EBS volume in `eu-west-1a` with `encrypted = true`.
- **`BC-03.tf` (Permissions Control)**: A least-privilege IAM policy allowing only `s3:GetObject` on a single private bucket path.
- **`BC-04.tf` (Network Control)**: A security group allowing only HTTPS (TCP port `443`) from the private network `10.0.0.0/8`.
