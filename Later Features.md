# Later Features

What's NOT currently cached but could be valuable:
- Column statistics (min/max/mean, distinct counts) from column analysis
- Query execution history/templates
- Performance metrics per table (query times)
- Inferred column purposes with confidence scores

## What I Want

- A way to save manual or agent-generated context (purpose, relationships, etc.)
- A way to save column descriptions/meanings
- A way to save other metadata relating to business context
- A way to save common query patterns and use cases (e.g. looking for lab tests - use query template combining LabComponentResultFact, LabComponentDim, ProcedureDim, and PatientDim. Know what columns mean and when to use them. Know that e.g. "HHV6 Tests" means (test 001, test 002, test 003) in a specific context. Add to this over time as additional context is discovered.)
- The above has not been thought through fully yet - need to consider how to structure and retrieve this info effectively.