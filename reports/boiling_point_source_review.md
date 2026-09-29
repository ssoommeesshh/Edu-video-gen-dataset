# Boiling-point pilot: source review

Experiment: `chem_12_101`, Manual of Microscale Chemistry Laboratory Kit, Experiment 1.1. Source: `Manual_01.pdf`, printed pages **17-18**, PDF pages **28-29**, Figure **1.1**.

**Status: agent visual source review completed; human scientific review pending.** Both rendered pages were inspected and the original PDF SHA-256 matched the ingested manual. The JSON companion records 27 individual claims, exact quotes, page IDs, rationales, source hashes, and unresolved items. No other experiment's scientific prose was edited.

| Catalog step | Source basis | What is now represented |
| --- | --- | --- |
| 1: prepare the setup | Printed 17, procedure 1-3; printed 18, procedure 4-5 and precautions; Fig. 1.1 | 50 mL beaker half-filled with water; sealed-end capillary, liquid sample, ignition tube and thermometer relationships; immersion and no-contact conditions |
| 2: gentle heating | Printed 18, procedure 6-7 | Gently heat the beaker; watch for a regular stream of bubbles in the ignition tube |
| 3: record the endpoint | Printed 18, procedure 7 | Read the thermometer when the regular stream of bubbles appears; no numerical reading is invented |

The three old observation placeholders did not describe supported observations. They were replaced with the setup state and the specific bubbling/temperature endpoint. The old vapour-escape wording was replaced with the manual's visible bubble criterion. Materials are now separate source-linked entries instead of one comma-separated string.

The manual leaves measured results blank. Its printed literature values have not been independently validated and are excluded from pilot prompts. Source fidelity is distinct from establishing scientific correctness.

The previous `approve_vertical_slice.py` shortcut described itself as a lenient integration approval and marked every claim verified. It now exits without changing data. Explicit reviews bind to the canonical claim and exact quoted passages, and the graph no longer carries one page's approval into the next page.

## Next input: one scene image

The pilot has one independent scene (`chem_12_101_scene`). No real candidate image has been selected yet. Use Fig. 1.1 to review one candidate for the beaker, wire gauze, tripod, clamped thermometer, tied ignition tube, capillary orientation, and immersion/no-contact relationships. Record its origin, permitted use, and reviewer decision. The manual diagram is a reference, not an automatically approved or licensed video input.

Step 1 groups five preparation actions. An image of the already assembled apparatus cannot automatically illustrate all of those actions. Decide the filmed starting state before choosing the real image and splitting/timing motion clips. The one-second CPU clips prove software behavior only.

## Remaining work

Human review of the source mapping and sample choice; one suitable real scene image; a filmed action plan and duration calibration; one short real generation; visual checks of apparatus and motion. Broad catalog review, large image collection, and prompt tuning remain deferred.
