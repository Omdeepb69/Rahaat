/**
 * Central State Store for Operator Console.
 */

export class ConsoleState {
  constructor() {
    this.activeWorkspace = "reports";
    this.selectedIncidentId = null;
    this.selectedReportId = null;
    this.reports = [];
    this.incidents = [];
    this.resources = [];
    this.assignments = [];
    this.listeners = new Map();
  }

  on(event, callback) {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, []);
    }
    this.listeners.get(event).push(callback);
  }

  emit(event, data) {
    if (this.listeners.has(event)) {
      this.listeners.get(event).forEach((cb) => cb(data));
    }
  }

  setWorkspace(workspace) {
    this.activeWorkspace = workspace;
    this.emit("workspace_changed", workspace);
  }

  setReports(reports) {
    this.reports = reports;
    this.emit("reports_updated", reports);
  }

  addReport(report) {
    this.reports.unshift(report);
    this.emit("report_added", report);
  }

  setIncidents(incidents) {
    this.incidents = incidents;
    this.emit("incidents_updated", incidents);
  }

  selectIncident(id) {
    this.selectedIncidentId = id;
    this.emit("incident_selected", id);
  }

  setResources(resources) {
    this.resources = resources;
    this.emit("resources_updated", resources);
  }
}
