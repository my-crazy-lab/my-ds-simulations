# Incident Postmortem Template

## Incident Summary

**Incident ID:** `INC-YYYY-MM-DD-XXX`  
**Title:** Brief description of the incident  
**Severity:** Critical | High | Medium | Low  
**Start Time:** YYYY-MM-DD HH:MM:SS UTC  
**End Time:** YYYY-MM-DD HH:MM:SS UTC  
**Duration:** X hours Y minutes  
**Status:** Resolved | Investigating | Monitoring  

## Executive Summary

Brief 2-3 sentence summary of what happened, the impact, and the resolution.

## Impact Assessment

### Customer Impact
- **Users Affected:** X users (Y% of total user base)
- **Services Affected:** List of affected services
- **Geographic Impact:** Regions/countries affected
- **Business Impact:** Revenue loss, SLA breaches, etc.

### Internal Impact
- **Engineering Teams Involved:** List teams
- **Person-Hours Spent:** Total effort across all teams
- **Systems Affected:** Infrastructure components impacted

### Metrics
- **Error Rate:** Peak error rate during incident
- **Latency Impact:** P95/P99 latency degradation
- **Availability:** Service availability percentage
- **Data Loss:** Any data loss or corruption

## Root Cause Analysis

### Primary Root Cause
Detailed explanation of the primary cause that led to the incident.

### Contributing Factors
1. **Factor 1:** Description of contributing factor
2. **Factor 2:** Description of contributing factor
3. **Factor 3:** Description of contributing factor

### Root Cause Categories
- [ ] Code Bug
- [ ] Configuration Error
- [ ] Infrastructure Failure
- [ ] Third-party Service
- [ ] Human Error
- [ ] Process Gap
- [ ] Monitoring Gap
- [ ] Capacity Issue

## Timeline

| Time (UTC) | Event | Action Taken | Person |
|------------|-------|--------------|--------|
| HH:MM | Incident detected via [alert/user report] | Initial investigation started | @engineer |
| HH:MM | Root cause identified | Mitigation plan developed | @engineer |
| HH:MM | Fix deployed to production | Monitoring recovery | @engineer |
| HH:MM | Service fully recovered | Incident resolved | @engineer |

## Detection and Response

### How was the incident detected?
- [ ] Automated monitoring alert
- [ ] Customer report
- [ ] Internal team discovery
- [ ] Third-party notification

### Detection Time
- **Time to Detection:** X minutes from start of incident
- **Time to Response:** X minutes from detection to first response
- **Time to Resolution:** X minutes from detection to full resolution

### What worked well?
- List things that worked well during incident response
- Effective monitoring/alerting
- Good communication
- Quick escalation

### What could be improved?
- List areas for improvement
- Monitoring gaps
- Communication issues
- Process improvements needed

## Technical Details

### System Architecture Context
Brief description of the affected system architecture and data flow.

### Failure Mode
Detailed technical explanation of how the failure occurred.

### Data Flow Impact
```
Normal Flow:
Service A → Service B → Service C → Database

Failed Flow:
Service A → Service B ❌ → Service C (timeout) → Database (inconsistent state)
```

### Error Messages and Logs
```
Key error messages and log entries that helped identify the issue
```

### Monitoring and Metrics
- **Key Metrics During Incident:**
  - Error rate: X%
  - Latency P95: Xms
  - CPU utilization: X%
  - Memory usage: X%

## Resolution

### Immediate Actions Taken
1. **Action 1:** Description and outcome
2. **Action 2:** Description and outcome
3. **Action 3:** Description and outcome

### Long-term Fix
Description of the permanent solution implemented.

### Verification
How was the fix verified to ensure the incident was fully resolved?

## Lessons Learned

### What went well?
1. **Positive aspect 1:** Description
2. **Positive aspect 2:** Description
3. **Positive aspect 3:** Description

### What didn't go well?
1. **Issue 1:** Description and impact
2. **Issue 2:** Description and impact
3. **Issue 3:** Description and impact

### Key Insights
- Important technical or process insights gained
- Systemic issues discovered
- Knowledge gaps identified

## Action Items

| Action Item | Owner | Priority | Due Date | Status |
|-------------|-------|----------|----------|--------|
| Implement monitoring for X | @engineer | High | YYYY-MM-DD | Open |
| Update runbook for Y | @sre | Medium | YYYY-MM-DD | Open |
| Add alerting for Z | @engineer | High | YYYY-MM-DD | Open |
| Review process for A | @manager | Low | YYYY-MM-DD | Open |

### Prevention Measures
1. **Technical Improvements:**
   - Code changes to prevent recurrence
   - Infrastructure improvements
   - Monitoring enhancements

2. **Process Improvements:**
   - Updated procedures
   - Training requirements
   - Communication improvements

3. **Monitoring Improvements:**
   - New alerts to add
   - Dashboard updates
   - SLO/SLI refinements

## Supporting Information

### Related Incidents
- Links to similar past incidents
- Patterns or trends identified

### External References
- Documentation links
- Third-party service status pages
- Relevant technical articles

### Attachments
- Screenshots of dashboards
- Log files
- Configuration files
- Communication threads

## Sign-off

**Incident Commander:** @name - Date  
**Technical Lead:** @name - Date  
**Engineering Manager:** @name - Date  
**SRE Lead:** @name - Date  

---

## Postmortem Review Process

1. **Draft Review:** Technical team reviews for accuracy
2. **Management Review:** Engineering leadership review
3. **Cross-team Review:** Other affected teams provide input
4. **Final Approval:** Incident commander approves final version
5. **Distribution:** Share with relevant stakeholders
6. **Follow-up:** Track action item completion

## Template Usage Notes

- Fill out all applicable sections
- Be specific and factual, avoid blame
- Focus on systemic improvements
- Include concrete action items with owners and dates
- Review and update the template based on lessons learned

---

*This postmortem template is based on industry best practices and should be customized for your organization's specific needs.*
