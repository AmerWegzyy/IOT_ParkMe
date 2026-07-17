# ParkMe Documentation — Start Here

One page telling you which document to open for what, in a sensible reading order.

## Understand the project

| # | Document | What it gives you |
|---|---|---|
| 1 | [SYSTEM_EXPLAINED.md](SYSTEM_EXPLAINED.md) | **The deep dive** — how everything works and *why* it was built this way: ESP-NOW vs cables, dual-core design, calibration, WiFi-loss handling, buffers/PSRAM/NVS, how the boards talk to each other and to the cloud. Read this to present or defend the project. |
| 2 | [PROJECT_OVERVIEW.md](PROJECT_OVERVIEW.md) | **The reference** — every API endpoint, Firestore collection, timing constant, sentinel state, and component, with file paths. Look things up here. |
| 3 | [USER_STORIES.md](USER_STORIES.md) | The requirements the project is graded against (11 user stories + extras, with acceptance criteria). |
| 4 | [USER_STORY_IMPLEMENTATION_AUDIT.md](USER_STORY_IMPLEMENTATION_AUDIT.md) | Honest code-first audit against those requirements: what's DONE / PARTIAL / MISSING, with evidence, risks, and a prioritized fix backlog. |
| ★ | [DEMO_PRESENTATION_SCRIPT.md](DEMO_PRESENTATION_SCRIPT.md) | **The staff demo run-of-show** — setup checklist, live scenario with speaking notes, the testing story, the parallel multi-spot simulation segment, Q&A prep, and mid-demo emergency fixes. |

## Run and test it

| # | Document | What it gives you |
|---|---|---|
| 5 | [TESTING_GUIDE.md](TESTING_GUIDE.md) | **How to test everything** — automated tests, end-to-end scenarios, failure/recovery drills with correct timings, the demo-day smoke checklist, and the "C1 suddenly offline" emergency fix. |
| 6 | [LOCAL_TESTING_GUIDE.md](LOCAL_TESTING_GUIDE.md) | Running the backend on your PC and pointing the boards at it (local development loop). |
| 7 | `Backend/simulate_spots.py` | Simulate the whole parking lot (spots A1–C2) with one command — real heartbeats and real photos through the real OCR pipeline, so the dashboard looks alive with only one physical device. `python Backend/simulate_spots.py --help` |
| 8 | [../ESP32/hardware-upload-guide.md](../ESP32/hardware-upload-guide.md) + [../ESP32/README.md](../ESP32/README.md) | Flashing the boards, calibration procedure, pins. |
| 9 | [../Unit Tests/README.md](../Unit%20Tests/README.md) | Hardware bring-up sketches (ultrasonic, OLED, camera) with PASS/FAIL serial output. |

## Deploy and operate the cloud

| # | Document | What it gives you |
|---|---|---|
| 10 | [step_by_step_deployment.md](step_by_step_deployment.md) | Every action to deploy from scratch (Cloud Run + Firebase Hosting), with commands. |
| 11 | [CLOUD_DEPLOYMENT_GUIDE.md](CLOUD_DEPLOYMENT_GUIDE.md) | Deployment reference: SECRETS.h checklist, critical flags, and a 15-problem troubleshooting table. |
| 12 | [cloud_setup_complete_guide.md](cloud_setup_complete_guide.md) | Post-deployment operations: the live URLs, updating boards, costs, and teardown when the course ends. |

## Live system

- Dashboard: <https://parkme-technion-f280b.web.app>
- Backend: `https://parkme-backend-31114651685.me-west1.run.app` (`/docs` for the API)

> ⚠️ Operational warning that outranks everything else: **do not run `Backend/seed_firestore.py` casually** — it wipes all parking spots including the real hardware MACs on C1. See TESTING_GUIDE §9 for the recovery command.
