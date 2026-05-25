# Security Incident Response Plan
## NarayanAstroReader — Phase 1

**Version:** 1.0  
**Date:** May 2026  
**Classification:** CONFIDENTIAL — Internal Use Only  
**Required by:** Architecture Specification §9.7 (Arch §9.7 pre-production blocker)

---

## 1. Purpose & Scope

This document defines the procedures for detecting, containing, eradicating, recovering from, and communicating about security incidents affecting the NarayanAstroReader platform.

This plan covers all systems in scope:
- API gateway and backend microservices
- PostgreSQL database (user PII, wallet balances, payment records)
- Redis (token blacklists, session cache)
- S3 report storage
- Authentication service (JWT, OAuth tokens)
- Payment gateway integration (Razorpay / Stripe)
- React SPA frontend (CDN-hosted)

**This plan is a mandatory pre-production requirement per Arch §9.7.** It must be reviewed and approved before Phase 1 go-live.

---

## 2. Incident Severity Classification

| Severity | Definition | Examples | SLA |
|----------|------------|----------|-----|
| **P0 — Critical** | Active breach, data exfiltration, or complete service outage | Database dump in progress; JWT signing key compromised; ransomware | Respond in **15 minutes** |
| **P1 — High** | Significant security event or partial outage | Brute-force success; payment webhook forgery; mass account takeover | Respond in **1 hour** |
| **P2 — Medium** | Limited impact, no confirmed breach | Unusual traffic pattern; single account compromise; dependency CVE exploited | Respond in **4 hours** |
| **P3 — Low** | No immediate impact | CVE reported but not exploited; phishing attempt; suspicious probe | Respond in **24 hours** |

---

## 3. Incident Response Team

| Role | Responsibility | Contact |
|------|---------------|---------|
| **Incident Commander (IC)** | Overall coordination; declares severity; approves public comms | CTO / Engineering Lead |
| **Security Lead** | Technical containment and forensics | Senior Backend Engineer |
| **DevOps Lead** | Infrastructure isolation, failover, log preservation | DevOps Engineer |
| **Product Lead** | User communication, stakeholder updates | Product Manager |
| **Legal / Compliance** | GDPR/DPDP breach notification decisions | Legal Counsel |

**On-call rotation:** Managed via PagerDuty. All P0/P1 pages go to the IC and Security Lead simultaneously.

---

## 4. Phase 1 — Detection

### 4.1 Detection Sources

| Source | What It Detects |
|--------|----------------|
| Prometheus + PagerDuty alerts | Elevated error rates, p99 latency spikes, circuit breaker trips |
| AWS CloudWatch anomaly detection | Unusual API call patterns, IAM privilege escalation |
| AWS WAF logs | SQLi / XSS attempts, unusual geographic traffic |
| Rate limiter alerts (backend/api/rate_limiter.py) | Brute-force on `/auth/login`, `/admin` |
| admin_audit.log monitoring | Unexpected admin actions |
| User reports | Account takeover reports via support@narayanastro.com |
| Third-party security scanner | GitHub Dependabot, Trivy CVE alerts in CI/CD |

### 4.2 Immediate Response on Detection

1. **Page the on-call engineer** (PagerDuty P0/P1 alert).
2. **Do not dismiss or ignore** any alert until investigated.
3. **Preserve evidence first** — before any remediation:
   - Export relevant CloudWatch log streams.
   - Take RDS snapshots (if DB compromise suspected).
   - Capture Kubernetes pod logs: `kubectl logs -n production <pod> --previous`
4. **Declare severity** using the table in Section 2.
5. **Open a private Slack incident channel**: `#incident-YYYY-MM-DD-<description>`
6. **Assign an Incident Commander** who owns the channel and timeline.

---

## 5. Phase 2 — Containment

### 5.1 P0 — Critical Containment (target: within 15 minutes)

| Action | Command / Procedure |
|--------|---------------------|
| **Block all external traffic** | Set ALB target group weight to 0 (blue/green) or enable WAF emergency rule |
| **Rotate JWT signing secret** | Set new `JWT_SECRET` in AWS Secrets Manager; restart all API pods — invalidates ALL tokens |
| **Rotate database password** | AWS RDS → Modify → Master password; update Secrets Manager |
| **Disable compromised admin account** | `POST /admin/user/{email}` with confirmation token, or direct DB update |
| **Enable maintenance mode** | Return HTTP 503 from health endpoint to pull pods from LB |
| **Isolate compromised pod** | `kubectl cordon <node>` + `kubectl delete pod <pod> -n production` |

### 5.2 P1 — High Containment (target: within 1 hour)

| Suspected Incident | Containment Action |
|-------------------|--------------------|
| Brute-force attack | Tighten rate limiter thresholds via env var; block attacking IP range in WAF |
| Payment webhook forgery | Disable payment webhook endpoint; rotate Razorpay/Stripe webhook secret |
| Account takeover | Force-logout affected user (`POST /admin/wallet/adjust` blacklist tokens); force email re-verification |
| Dependency CVE exploited | Emergency pip/npm upgrade; rebuild + deploy image |
| Data scraping via API | Add rate limiting to affected endpoints; require additional auth |

### 5.3 Containment Checklist

- [ ] Incident severity declared and IC assigned
- [ ] Evidence preserved (logs, snapshots)
- [ ] Affected systems isolated or traffic blocked
- [ ] Credentials rotated (as applicable)
- [ ] Security team fully briefed
- [ ] Legal/compliance notified (for P0/P1 involving PII)

---

## 6. Phase 3 — Eradication

1. **Root cause analysis (RCA):** Identify the vulnerability or failure mode.
2. **Remove malicious artefacts:** Malware, backdoors, injected code, rogue admin accounts.
3. **Patch the vulnerability:**
   - Dependency CVE → update package + rebuild image
   - Code vulnerability → hotfix branch → emergency deploy
   - Misconfiguration → update Terraform + apply
4. **Verify patch:** Run the full CI/CD security pipeline (CVE scan + SAST + tests).
5. **Penetration test (P0/P1):** Commission targeted re-test of the affected component.

---

## 7. Phase 4 — Recovery

1. **Restore from clean backup** if data integrity is in doubt:
   - PostgreSQL: restore from RDS PITR snapshot taken **before** the incident.
   - S3: restore from versioned backup.
2. **Gradually restore traffic:**
   - Start with 5% blue/green traffic shift.
   - Monitor error rates and anomalous queries for 30 minutes.
   - Scale to 100% only when metrics are normal.
3. **Re-enable services** in order: auth → wallet → kundli → AI → payment.
4. **Force re-authentication** for all users if JWT secret was rotated.
5. **Verify wallet ledger integrity:** Check for unintended credits or debits during incident window.

---

## 8. Phase 5 — User Notification

### 8.1 Breach Notification Requirements

| Jurisdiction | Regulation | Notification Deadline | Threshold |
|-------------|------------|----------------------|-----------|
| India | DPDP Act 2023 | 72 hours to CERT-In | Any breach of personal data |
| EU users | GDPR Article 33 | 72 hours to supervisory authority | Breach affecting EU residents |
| All users | Platform policy | Within 72 hours | Any confirmed PII exposure |

### 8.2 Notification Template (Email to Affected Users)

```
Subject: Important security notice from NarayanAstroReader

Dear [Name],

We are writing to inform you of a security incident that may have affected your account.

What happened: [Brief description — what data, what period, how discovered]

What data was involved: [Specifically: name / email / birth data / wallet balance / payment history]

What we have done: [Containment and fix actions taken]

What you should do:
  1. Change your password immediately at: https://app.narayanastro.com/reset-password
  2. Review your wallet transaction history for any unauthorised changes.
  3. If you used the same password elsewhere, change it there too.

We sincerely apologise for this incident. Your trust is our highest priority.

If you have questions, contact: security@narayanastro.com

— The NarayanAstroReader Team
```

### 8.3 Notification Not Required

User notification is **not required** if:
- No personal data was accessed (e.g., brute-force attempt that failed).
- Data was rendered unreadable due to encryption (AES-256 KMS).
- Affected only anonymous / aggregated analytics data.

*Document this decision in the incident log with justification.*

---

## 9. Phase 6 — Post-Incident Review

Within **5 business days** of incident closure:

1. **Timeline reconstruction:** Minute-by-minute log of events, actions, and decisions.
2. **Root cause:** Technical and process root cause identified.
3. **Impact assessment:**
   - Number of affected users
   - Data categories exposed
   - Financial impact (wallet/payment anomalies)
   - Regulatory exposure
4. **Lessons learned:** What worked, what didn't.
5. **Action items:** Concrete fixes with owners and due dates.
6. **Update this plan** if gaps were identified.

Post-incident review document is stored in: `docs/incident-reviews/YYYY-MM-DD-<title>.md`

---

## 10. Contact & Escalation

| Contact | When to Use |
|---------|-------------|
| `#incident-*` Slack channel | All incident communication (P0–P2) |
| PagerDuty on-call | P0/P1 immediate page |
| `security@narayanastro.com` | External reports; user security enquiries |
| `legal@narayanastro.com` | GDPR/DPDP breach notification |
| AWS Support (Business/Enterprise) | AWS infrastructure incidents |
| Razorpay fraud team | Payment fraud incidents |
| Stripe Trust & Safety | Stripe payment fraud incidents |
| CERT-In (India) | `incident@cert-in.org.in` — mandatory for DPDP breaches |

---

## 11. Plan Maintenance

| Activity | Frequency | Owner |
|----------|-----------|-------|
| Plan review and update | Quarterly | Security Lead |
| Tabletop exercise | Semi-annually | Incident Commander |
| Contact list verification | Monthly | DevOps Lead |
| Post-incident plan update | After every P0/P1 | IC + Security Lead |

**This plan must be re-approved after any major infrastructure change.**

---

*Approved by: [Name / Role] — [Date]*  
*Next review: Q3 2026*
