# Built-in icons

108 vendor-neutral hand-drawn icons in the Field Notes style, each one grouped item of native
Excalidraw shapes on a 100 x 100 grid. Use them for any architecture, DDD or operations
diagram. Look an icon up by key in `manifest.json`; its shapes are the item with id
`lib-<key>` in `architecture-generic-hand-drawn.excalidrawlib`.

- **Systems and infrastructure:** `datastore`, `service`, `api`, `queue`, `event-bus`,
  `gateway`, `cloud`, `cache`, `ui-screen`, `mobile-device`.
- **General tech:** `archive`, `database`, `json-file`, `documents`, `layers`, `hexagon`,
  `chip`, `lock`, `load-balancer`, `code`, `server-rack`, `browser`, `dns`, `vpc`,
  `private-subnet`, `public-subnet`, `user`, `users`, `device`, `server`, `email`,
  `cad-3d`, `question-mark`, `reinforcement-learning`, `sim-to-real`.
- **People and external parties:** `person`, `team`, `external-org`, `external-system`.
- **Devices:** `sensor`, `controller`.
- **Robotics and physical:** `robot`, `amr`, `forklift`, `machine`.
- **Flow and time:** `decision`, `document`, `clock`, `timer`, `alert`, `message`, `dag`,
  `gantt-chart`.
- **DDD and EventStorming,** in the standard colours: `domain-event` (orange), `command`
  (blue), `policy` (violet), `aggregate` (yellow), `read-model` (green), `hotspot` (red),
  `bounded-context` (neutral).
- **Cloud services,** vendor-neutral: `cloud-compute`, `cloud-functions`,
  `cloud-containers`, `cloud-kubernetes`, `cloud-object-storage`, `cloud-block-storage`,
  `cloud-file-storage`, `cloud-sql-database`, `cloud-nosql-database`, `cloud-cache`,
  `cloud-data-warehouse`, `cloud-queue`, `cloud-pub-sub`, `cloud-event-bus`,
  `cloud-streaming`, `cloud-api-gateway`, `cloud-cdn`, `cloud-load-balancer`, `cloud-dns`,
  `cloud-iam`, `cloud-secrets`, `cloud-monitoring`, `cloud-vpc`, `cloud-firewall`,
  `cloud-container-registry`, `cloud-workflow`, `cloud-machine-learning`.
- **Status and operations:** `status-planned`, `status-in-progress`, `status-waiting`,
  `status-passed`, `status-failed`, `status-rework` (use these for the status rule in
  SKILL.md), plus `polling`, `dollar-sign`, `speedometer`, `traceability`, `compliance`,
  `governance`, `provenance`, `uptime`, `change`, `comparison`, `flag`, `readings`,
  `logs`, `metrics`, `alert-bell`.

People editing by hand can import the `.excalidrawlib` file into their Excalidraw library
(Library panel, ⋯ menu, Open).
