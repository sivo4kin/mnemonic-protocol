describe('Memory Explorer', () => {
  let workspaceId: string

  beforeEach(() => {
    cy.resetDb()
    cy.createWorkspace('Explorer Test').then(ws => {
      workspaceId = ws.workspace_id
      // Seed memories
      cy.saveMemory(workspaceId, 'TurboQuant uses random rotation and scalar quantization', 'finding', 'TurboQuant method')
      cy.saveMemory(workspaceId, 'Decided to use fastembed as canonical embedder', 'decision', 'Embedder decision')
      cy.saveMemory(workspaceId, 'What is the optimal bit-width for V1?', 'question', 'Bit-width question')
      cy.saveMemory(workspaceId, 'arXiv:2504.19874 TurboQuant paper', 'source', 'TurboQuant paper')
    })
  })

  it('lists all memories', () => {
    cy.visit(`/workspace/${workspaceId}/memory`)
    cy.contains('Memory Explorer')
    cy.contains('TurboQuant method')
    cy.contains('Embedder decision')
    cy.contains('Bit-width question')
    cy.contains('TurboQuant paper')
  })

  it('can filter by memory type', () => {
    cy.visit(`/workspace/${workspaceId}/memory`)

    // Filter to questions only
    cy.get('select').last().select('question')
    cy.contains('Bit-width question')
    cy.contains('TurboQuant method').should('not.exist')
  })

  it('can search memories', () => {
    cy.visit(`/workspace/${workspaceId}/memory`)

    cy.get('input[placeholder="Search memories..."]').type('quantization')
    cy.contains('Search').click()

    // Should show results with relevance scores
    cy.get('[class*="rounded-xl"]').should('have.length.at.least', 1)
  })

  it('can view memory detail', () => {
    cy.visit(`/workspace/${workspaceId}/memory`)

    // Click on a memory
    cy.contains('TurboQuant method').click()

    // Detail panel should show
    cy.contains('TurboQuant uses random rotation and scalar quantization')
    cy.contains('finding')
  })

  it('can navigate back to workspace', () => {
    cy.visit(`/workspace/${workspaceId}/memory`)
    cy.contains('Workspace').click()
    cy.url().should('include', `/workspace/${workspaceId}`)
    cy.url().should('not.include', '/memory')
  })
})
