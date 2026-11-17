window.claimDemo = {
  "examples": {
    "rodents": {
      "title": "Two outcomes from one meta-analysis",
      "reference": "Neural stem/progenitor cell therapy in preclinical rodent models",
      "source_url": "https://link.springer.com/article/10.1186/s13287-022-03231-1",
      "study": "Rezk et al. · reference 44",
      "before": "2023-08-01",
      "direct": [
        {
          "id": "rodent-rat",
          "claim": "Use the pooled rat cognitive-function result from the cited review in our synthesis.",
          "action": "no_notice_as_of",
          "findings": [],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.1186/s13287-022-03231-1"
          ],
          "unresolved_references": []
        },
        {
          "id": "rodent-mouse",
          "claim": "Use the pooled mouse cognitive-function result from the cited review in our synthesis.",
          "action": "no_notice_as_of",
          "findings": [],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.1186/s13287-022-03231-1"
          ],
          "unresolved_references": []
        }
      ],
      "current": [
        {
          "id": "rodent-rat",
          "claim": "Use the pooled rat cognitive-function result from the cited review in our synthesis.",
          "action": "review_indirect",
          "findings": [
            {
              "path": [
                "10.1186/s13287-022-03231-1",
                "10.1007/s11011-021-00890-6"
              ],
              "notice": {
                "ref": "10.1186/s13287-022-03231-1",
                "doi": "10.1007/s11011-021-00890-6",
                "kind": "retraction",
                "date": "2023-08-29",
                "url": "https://doi.org/10.1007/s11011-023-01282-8"
              },
              "evidence": {
                "id": "rodent-rat-mwm",
                "role": "uses",
                "locator": "Results, Cognitive function, Figure 3b and reference 44",
                "url": "https://link.springer.com/article/10.1186/s13287-022-03231-1#Fig3",
                "finding": "The rat cognitive-function pool lists references 37–44. The retracted Rezk study is reference 44.",
                "basis": "primary_source"
              },
              "action": "review_indirect"
            }
          ],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.1186/s13287-022-03231-1"
          ],
          "unresolved_references": [],
          "recorded_revision": "The pooled rat cognitive-function result in the cited review (Results, Figure 3b) includes reference 44, the Rezk study, which was retracted on 2023-08-29. Any synthesis using this pooled rat result must exclude or explicitly qualify that retracted study."
        },
        {
          "id": "rodent-mouse",
          "claim": "Use the pooled mouse cognitive-function result from the cited review in our synthesis.",
          "action": "retain_for_this_notice",
          "findings": [
            {
              "path": [
                "10.1186/s13287-022-03231-1",
                "10.1007/s11011-021-00890-6"
              ],
              "notice": {
                "ref": "10.1186/s13287-022-03231-1",
                "doi": "10.1007/s11011-021-00890-6",
                "kind": "retraction",
                "date": "2023-08-29",
                "url": "https://doi.org/10.1007/s11011-023-01282-8"
              },
              "evidence": {
                "id": "rodent-mouse-mwm",
                "role": "outside_scope",
                "locator": "Results, Cognitive function, Figure 3a",
                "url": "https://link.springer.com/article/10.1186/s13287-022-03231-1#Fig3",
                "finding": "The mouse cognitive-function pool lists 19 mouse studies. Reference 44 contributes to the separate rat pool.",
                "basis": "primary_source"
              },
              "action": "retain_for_this_notice"
            }
          ],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.1186/s13287-022-03231-1"
          ],
          "unresolved_references": [],
          "recorded_revision": "Use the pooled mouse cognitive-function result from the cited review in our synthesis."
        }
      ],
      "historical": [
        {
          "id": "rodent-rat",
          "claim": "Use the pooled rat cognitive-function result from the cited review in our synthesis.",
          "action": "no_notice_as_of",
          "findings": [],
          "as_of": "2023-08-01",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.1186/s13287-022-03231-1"
          ],
          "unresolved_references": []
        },
        {
          "id": "rodent-mouse",
          "claim": "Use the pooled mouse cognitive-function result from the cited review in our synthesis.",
          "action": "no_notice_as_of",
          "findings": [],
          "as_of": "2023-08-01",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.1186/s13287-022-03231-1"
          ],
          "unresolved_references": []
        }
      ]
    },
    "recommender": {
      "title": "Two claims from one recommender overview",
      "reference": "AI-driven transformation of e-commerce",
      "source_url": "https://wjaets.com/sites/default/files/fulltext_pdf/WJAETS-2025-0276.pdf#page=5",
      "study": "Shen et al. · reference 6",
      "direct": [
        {
          "id": "cs-shen-indirect",
          "claim": "Use the cited overview as evidence that improved K-means can segment users using both behavioral and social data.",
          "action": "no_notice_as_of",
          "findings": [],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.30574/wjaets.2025.15.1.0276"
          ],
          "unresolved_references": []
        },
        {
          "id": "cs-shen-unrelated-claim",
          "claim": "The cited overview describes separating candidate generation from ranking in production recommendation pipelines.",
          "action": "no_notice_as_of",
          "findings": [],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.30574/wjaets.2025.15.1.0276"
          ],
          "unresolved_references": []
        }
      ],
      "current": [
        {
          "id": "cs-shen-indirect",
          "claim": "Use the cited overview as evidence that improved K-means can segment users using both behavioral and social data.",
          "action": "review_indirect",
          "findings": [
            {
              "path": [
                "10.30574/wjaets.2025.15.1.0276",
                "10.1007/s44196-023-00321-7"
              ],
              "notice": {
                "ref": "10.30574/wjaets.2025.15.1.0276",
                "doi": "10.1007/s44196-023-00321-7",
                "kind": "retraction",
                "date": "2024-03-27",
                "url": "https://link.springer.com/article/10.1007/s44196-024-00476-x"
              },
              "evidence": {
                "id": "wjaets-kmeans-segmentation",
                "role": "uses",
                "locator": "Page 983, section 3.2 and reference 6",
                "url": "https://wjaets.com/sites/default/files/fulltext_pdf/WJAETS-2025-0276.pdf#page=5",
                "finding": "The overview attributes combined behavioral and social segmentation with improved K-means to the retracted Shen article.",
                "basis": "primary_source"
              },
              "action": "review_indirect"
            }
          ],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.30574/wjaets.2025.15.1.0276"
          ],
          "unresolved_references": [],
          "recorded_revision": "The cited overview attributes the claim that improved K-means can segment users using both behavioral and social data to a source article (10.1007/s44196-023-00321-7) that was retracted on 2024-03-27. It should not be used as independent evidence for this claim without that qualification."
        },
        {
          "id": "cs-shen-unrelated-claim",
          "claim": "The cited overview describes separating candidate generation from ranking in production recommendation pipelines.",
          "action": "retain_for_this_notice",
          "findings": [
            {
              "path": [
                "10.30574/wjaets.2025.15.1.0276",
                "10.1007/s44196-023-00321-7"
              ],
              "notice": {
                "ref": "10.30574/wjaets.2025.15.1.0276",
                "doi": "10.1007/s44196-023-00321-7",
                "kind": "retraction",
                "date": "2024-03-27",
                "url": "https://link.springer.com/article/10.1007/s44196-024-00476-x"
              },
              "evidence": {
                "id": "wjaets-candidate-ranking",
                "role": "outside_scope",
                "locator": "Page 983, section 3.3 and reference 5",
                "url": "https://wjaets.com/sites/default/files/fulltext_pdf/WJAETS-2025-0276.pdf#page=5",
                "finding": "The overview attributes the two-stage recommendation architecture to Loukili (reference 5). Shen is reference 6 in the preceding section.",
                "basis": "primary_source"
              },
              "action": "retain_for_this_notice"
            }
          ],
          "as_of": "2026-11-16",
          "snapshot_date": "2026-11-16",
          "resolved_references": [
            "10.30574/wjaets.2025.15.1.0276"
          ],
          "unresolved_references": [],
          "recorded_revision": "The cited overview describes separating candidate generation from ranking in production recommendation pipelines."
        }
      ]
    }
  },
  "actions": {
    "review_direct": "Review the direct citation",
    "review_indirect": "Reassess the cited outcome",
    "review_notice": "Review the publication notice",
    "retain_with_notice": "Retain with the notice",
    "retain_for_this_notice": "Outside the scope of this notice",
    "no_notice_as_of": "No applicable notice in the snapshot at this date",
    "insufficient_evidence": "Insufficient evidence"
  },
  "pilot": {
    "direct": {
      "cases": 17,
      "returned": 17,
      "exact_actions": 6,
      "required_review_actions": 11,
      "correct_review_actions": 5,
      "false_alerts_on_controls": 1,
      "indirect_detected": 0,
      "indirect_total": 6
    },
    "untyped": {
      "cases": 17,
      "returned": 17,
      "exact_actions": 12,
      "required_review_actions": 11,
      "correct_review_actions": 11,
      "false_alerts_on_controls": 5,
      "indirect_detected": 6,
      "indirect_total": 6
    },
    "claim_aware": {
      "cases": 17,
      "returned": 17,
      "exact_actions": 17,
      "required_review_actions": 11,
      "correct_review_actions": 11,
      "false_alerts_on_controls": 0,
      "indirect_detected": 6,
      "indirect_total": 6
    }
  },
  "agent": "Claude Haiku 5.5",
  "source_sha256": "a9f3d21b0d9cbabffbe42b1604891fddbee7aa013890fd0c2b605e1dbfb414f5",
  "snapshot_sha256": "1cf26f35128e4881d4f9f4777e5c7a2999dbfdfab8fd9a92b830e8a028c3910e"
};
