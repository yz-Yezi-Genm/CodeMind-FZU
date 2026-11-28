# Beta live integration synthetic corpus

This directory contains synthetic data for the opt-in Stage 2 Qwen integration
check only. The source URL uses the reserved `.invalid` domain and is not a
formal policy package. It must never be copied into
`knowledge_base/processed/alpha/approved/`.

The package sets `temporal_notes.human_approved=true` only to exercise the
existing loader and Agent review gates. This is a synthetic test flag, not a
claim of real human approval or formal policy sign-off. The production review
mechanism and all approval gates remain unchanged.
