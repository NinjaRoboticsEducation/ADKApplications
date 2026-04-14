# Format Contract

Use this reference when restructuring a raw transcript with `yttranscript-optimizer`.

## Required output skeleton

```markdown
## Structured Transcript

### Section 1: <subtitle>
<verbatim transcript block 1>

### Section 2: <subtitle>
<verbatim transcript block 2>

## Key Takeaways
- <summary bullet>
- <summary bullet>
```

## Allowed additions

- One top-level transcript heading: `## Structured Transcript`
- One section subtitle per block: `### Section N: <subtitle>`
- Blank lines between blocks
- One summary heading: `## Key Takeaways`
- Summary bullets after the transcript

## Forbidden changes inside transcript blocks

- Rewriting words
- Dropping words
- Translating words
- Fixing grammar
- Reordering lines
- Compressing repetitions
- Replacing timestamps or speaker labels

## Preservation standard

The transcript body must match the raw source after whitespace normalization once the structural marker lines are removed. This means:

- The same words appear in the same order.
- The same timestamps or speaker labels appear in the same order.
- Only grouping and inserted headings change.

## Suggested workflow

1. Copy the raw transcript into a working draft.
2. Identify topic changes.
3. Insert `### Section N: ...` lines before each topic block.
4. Add blank lines between blocks.
5. Append `## Key Takeaways` after the transcript.
6. Run the validator.

## Validator assumptions

The bundled validator removes:

- `## Structured Transcript`
- `### Section N: ...`
- `## Key Takeaways`
- lines starting with `- ` after the `## Key Takeaways` marker
- blank lines

Everything else is treated as transcript content and must remain in the same order as the raw source.
