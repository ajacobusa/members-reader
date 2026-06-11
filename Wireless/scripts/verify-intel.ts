// Unit checks for the alert-intelligence engine (pure module, no DB needed).
// Run with: npm run verify:intel
import {
  enrichAlert,
  groupAlerts,
  buildTimeline,
  bumpSeverity,
  playbookFor,
} from "../src/lib/alert-intel";
import { assessIotDevices, iotCounts, onIotSegment } from "../src/lib/iot-intel";
import {
  slaDueFor,
  slaState,
  formatSla,
  findRecurringWithoutIncident,
  findSlaBreaches,
} from "../src/lib/incidents";
import {
  contractExpiringSoon,
  contractExpired,
  milestoneProgress,
  checklistProgress,
} from "../src/lib/projects";
import { can, visibleProperties, ROLES, ACTIONS, type Actor } from "../src/lib/authz";
import { scoreTrend } from "../src/lib/health";
import type { Property } from "../src/db/schema";
import type {
  Alert,
  IotDevice,
  Incident,
  ProjectMilestone,
  ProjectChecklistItem,
} from "../src/db/schema";

function check(cond: boolean, label: string) {
  if (!cond) throw new Error(`FAILED: ${label}`);
  console.log(`  ✓ ${label}`);
}

// Minimal alert factory for test cases.
let n = 0;
function alert(over: Partial<Alert>): Alert {
  return {
    id: `t-${n++}`,
    propertyId: "p1",
    severity: "warning",
    status: "open",
    title: `Alert ${n}`,
    description: null,
    source: "aruba_central",
    category: "guest_wifi",
    externalId: null,
    raisedAt: new Date("2026-06-10T12:00:00Z"),
    resolvedAt: null,
    ...over,
  } as Alert;
}

console.log("1) Playbook coverage…");
check(playbookFor("rf").action.includes("RF plan"), "rf playbook gives the RF-plan action");
check(playbookFor(null).cause.includes("Not yet classified"), "null category falls back");
check(playbookFor("nonsense").action.length > 0, "unknown category falls back safely");

console.log("2) Severity rules…");
check(bumpSeverity("info") === "warning", "info escalates to warning");
check(bumpSeverity("warning") === "critical", "warning escalates to critical");
check(bumpSeverity("critical") === "critical", "critical stays critical");

console.log("3) Recurrence + escalation…");
const a1 = alert({});
const a2 = alert({ raisedAt: new Date("2026-06-05T12:00:00Z") }); // 5 days apart
const lone = alert({ propertyId: "p2", category: "rf", severity: "info" });
const all = [a1, a2, lone];
const e1 = enrichAlert(a1, all);
check(e1.recurring && e1.occurrences === 2, "2 same-category alerts in window → recurring");
check(e1.escalated && e1.effectiveSeverity === "critical", "recurring warning escalates to critical");
const eLone = enrichAlert(lone, all);
check(!eLone.recurring && eLone.effectiveSeverity === "info", "single alert keeps stored severity");
const old = alert({ raisedAt: new Date("2026-01-01T00:00:00Z") }); // outside 30d window
check(enrichAlert(a1, [a1, old]).recurring === false, "old occurrences outside window don't count");

console.log("4) Grouping…");
const groups = groupAlerts(all, (a) => a.category ?? "uncategorized");
check(groups[0].key === "guest_wifi" && groups[0].total === 2, "worst group sorts first");
check(groups[0].warning === 2, "per-severity counts correct");

console.log("5) Timeline…");
const resolved = alert({
  raisedAt: new Date("2026-06-09T00:00:00Z"),
  resolvedAt: new Date("2026-06-09T06:00:00Z"),
  status: "resolved",
});
const tl = buildTimeline([a1, resolved]);
check(tl.length === 3, "resolved alert contributes raised + resolved events");
check(tl[0].at.getTime() >= tl[tl.length - 1].at.getTime(), "timeline is newest-first");

console.log("6) IoT segmentation rules…");
// Minimal IoT device factory for test cases.
function iot(over: Partial<IotDevice>): IotDevice {
  return {
    id: `i-${n++}`,
    propertyId: "p1",
    name: `Device ${n}`,
    deviceType: "Sensor",
    vendor: "Generic",
    macAddress: null,
    vlan: 50,
    ssid: "IoT-Net",
    securityGroup: "iot-restricted",
    firewallZone: "iot",
    nacPolicy: "iot-restricted",
    owner: "Facilities",
    approval: "approved",
    status: "online",
    riskLevel: "low",
    lastSeen: new Date("2026-06-10T12:00:00Z"),
    createdAt: new Date("2026-01-01T00:00:00Z"),
    ...over,
  } as IotDevice;
}

const rogue = iot({
  approval: "unapproved",
  ssid: "Staff-Net",
  securityGroup: "staff",
  firewallZone: "corp",
});
const unreviewed = iot({ approval: "unapproved" }); // correctly segmented, not approved
const dark = iot({ status: "offline", riskLevel: "high" });
const clean = iot({});
const noZone = iot({ firewallZone: null });

check(!onIotSegment(rogue) && onIotSegment(clean), "segment detection distinguishes staff vs iot");
const fs = assessIotDevices([rogue, unreviewed, dark, clean, noZone]);
const rogueFinding = fs.find((f) => f.device === rogue);
check(
  rogueFinding?.severity === "critical" && rogueFinding.action.includes("IoT VLAN"),
  "unknown device on staff network → critical + quarantine/move action"
);
check(
  fs.find((f) => f.device === unreviewed)?.severity === "warning",
  "unapproved-but-segmented device → warning"
);
check(
  fs.find((f) => f.device === dark)?.severity === "critical",
  "offline high-risk device → critical"
);
check(fs.every((f) => f.device !== clean), "clean device produces no findings");
check(
  fs.find((f) => f.device === noZone)?.severity === "info",
  "missing firewall zone → info finding"
);
check(fs[0].severity === "critical", "findings sort worst-first");
const ic = iotCounts([rogue, unreviewed, dark, clean]);
check(ic.unapproved === 2 && ic.highRisk === 1, "rollup counts correct");

console.log("7) Ticketing workflow rules…");
// Minimal incident factory.
function incident(over: Partial<Incident>): Incident {
  return {
    id: `inc-${n++}`,
    propertyId: "p1",
    title: "Test incident",
    summary: null,
    status: "open",
    severity: "warning",
    category: "guest_wifi",
    alertId: null,
    owner: null,
    slaDueAt: new Date("2026-06-10T12:00:00Z"),
    openedAt: new Date("2026-06-10T00:00:00Z"),
    resolvedAt: null,
    ...over,
  } as Incident;
}
const NOW = new Date("2026-06-10T13:00:00Z"); // 1h past the test SLA deadline

// SLA math.
check(
  slaDueFor("critical", new Date("2026-06-10T00:00:00Z")).getTime() ===
    new Date("2026-06-10T04:00:00Z").getTime(),
  "critical SLA deadline is openedAt + 4h"
);
const breachedInc = incident({});
check(slaState(breachedInc, NOW).breached, "open incident past deadline is breached");
check(
  !slaState(incident({ status: "resolved" }), NOW).breached,
  "resolved incident never counts as breached"
);
check(formatSla(slaState(breachedInc, NOW)).includes("breached"), "SLA chip text says breached");

// Auto-create rule: recurring alerts without a covering incident.
const ga1 = alert({ category: "guest_wifi" });
const ga2 = alert({ category: "guest_wifi", raisedAt: new Date("2026-06-09T12:00:00Z") });
const single = alert({ category: "rf", propertyId: "p2" });
const candidates = findRecurringWithoutIncident([ga1, ga2, single], []);
check(
  candidates.length === 1 && candidates[0].category === "guest_wifi" && candidates[0].count === 2,
  "2 open same-category alerts with no incident → auto-create candidate"
);
const covered = findRecurringWithoutIncident(
  [ga1, ga2],
  [incident({ category: "guest_wifi", status: "investigating" })]
);
check(covered.length === 0, "an open incident with same property+category suppresses auto-create");
const resolvedCover = findRecurringWithoutIncident(
  [ga1, ga2],
  [incident({ category: "guest_wifi", status: "resolved" })]
);
check(resolvedCover.length === 1, "a resolved incident does NOT suppress auto-create");

// Auto-escalate rule.
const toEscalate = findSlaBreaches([breachedInc, incident({ status: "resolved" })], NOW);
check(
  toEscalate.length === 1 && toEscalate[0] === breachedInc,
  "only active incidents past SLA are escalated"
);

console.log("8) Vendor/project helpers…");
const T0 = new Date("2026-06-11T00:00:00Z");
check(
  contractExpiringSoon(new Date("2026-08-01T00:00:00Z"), T0),
  "contract ending in ~51 days flags as expiring soon"
);
check(
  !contractExpiringSoon(new Date("2027-06-01T00:00:00Z"), T0),
  "contract a year out does not flag"
);
check(
  !contractExpiringSoon(new Date("2026-06-01T00:00:00Z"), T0) &&
    contractExpired(new Date("2026-06-01T00:00:00Z"), T0),
  "past date counts as expired, not expiring-soon"
);
check(!contractExpiringSoon(null, T0), "null contract end never flags");

const ms = (completed: boolean): ProjectMilestone =>
  ({
    id: `m-${n++}`,
    projectId: "pr1",
    name: "m",
    dueDate: T0,
    completedAt: completed ? T0 : null,
    sortOrder: 0,
  }) as ProjectMilestone;
const prog = milestoneProgress([ms(true), ms(true), ms(false)]);
check(prog.done === 2 && prog.total === 3 && prog.pct === 67, "milestone progress 2/3 = 67%");
check(milestoneProgress([]).pct === 0, "empty milestone list is 0%, not NaN");

const cl = (done: number): ProjectChecklistItem =>
  ({ id: `cl-${n++}`, projectId: "pr1", phase: "cutover", label: "x", done, sortOrder: 0 }) as ProjectChecklistItem;
check(checklistProgress([cl(1), cl(0)]).pct === 50, "checklist progress 1/2 = 50%");

console.log("9) RBAC permission matrix…");
check(ROLES.length === 6, "six roles defined");
check(
  ACTIONS.every((a) => can("owner", a)) && ACTIONS.every((a) => can("admin", a)),
  "owner and admin can do everything"
);
check(
  can("readonly_exec", "view") &&
    can("readonly_exec", "ai.run") &&
    !can("readonly_exec", "incident.update") &&
    !can("readonly_exec", "project.toggle"),
  "read-only exec: view + AI only"
);
check(
  can("network_engineer", "incident.update") &&
    can("network_engineer", "project.toggle") &&
    !can("network_engineer", "integration.manage"),
  "network engineer works tickets/projects but not integrations"
);
check(
  can("vendor_msp", "incident.update") && !can("vendor_msp", "incident.create"),
  "vendor/MSP can work assigned tickets but not open new ones"
);
check(
  can("property_manager", "incident.create") && !can("property_manager", "incident.update"),
  "property manager can raise but not reassign incidents"
);
// @ts-expect-error — unknown role must be denied, not crash.
check(can("intruder", "view") === false, "unknown role is denied everything");

// Property-level scoping.
const props = [{ id: "p1" }, { id: "p2" }, { id: "p3" }] as Property[];
const scoped: Actor = { userId: "u1", name: "PM", role: "property_manager", propertyIds: ["p2"] };
const full: Actor = { userId: "u2", name: "Owner", role: "owner", propertyIds: null };
check(
  visibleProperties(scoped, props).length === 1 &&
    visibleProperties(scoped, props)[0].id === "p2",
  "scoped actor sees only allow-listed properties"
);
check(visibleProperties(full, props).length === 3, "null scope sees all properties");
check(
  visibleProperties({ ...scoped, propertyIds: [] }, props).length === 0,
  "empty allow-list sees nothing (company isolation default)"
);

console.log("10) Score trend (before/after)…");
const snapAt = (day: number, score: number) => ({
  score,
  at: new Date(`2026-06-${String(day).padStart(2, "0")}T06:00:00Z`),
});
const T1 = new Date("2026-06-10T12:00:00Z");
const series = [snapAt(3, 91), snapAt(5, 80), snapAt(8, 50)];
const tr = scoreTrend(series, 30, T1); // target = Jun 3 → closest is the 91
check(tr.weekAgo === 91 && tr.delta === -61, "picks the snapshot ~7 days back (91 → 30 = ▼61)");
check(
  scoreTrend([], 50, T1).weekAgo === null && scoreTrend([], 50, T1).delta === null,
  "no history → null trend (UI shows —)"
);
const up = scoreTrend([snapAt(3, 40)], 75, T1);
check(up.delta === 35, "improving property reports a positive delta");
const dayTrend = scoreTrend(series, 45, T1, 2); // target Jun 8 → closest is the 50
check(dayTrend.weekAgo === 50 && dayTrend.delta === -5, "window parameter selects nearer snapshots");

console.log("\nAll alert-intelligence checks passed.");
