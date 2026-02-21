## CHANGED Requirements

### Requirement: Socratic Prompt Generation
Previously, `src/socratic.py` mapped a single massive string to prompt the LLM to output DaisyUI HTML markup. The logic MUST change.

#### Scenario: Removing Custom UI Markup from Prompt
- **WHEN** the Socratic explainer constructs the Socratic UI Block.
- **THEN** it outputs structurally clean JSON without embedded `css` or `DaisyUI` utility classes. The formatting happens implicitly by passing the payload directly to the OpenWebUI ID-Message components.
