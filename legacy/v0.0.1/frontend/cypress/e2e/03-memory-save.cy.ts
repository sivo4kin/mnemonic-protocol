describe('Memory Save', () => {
  let workspaceId: string

  beforeEach(() => {
    cy.resetDb()
    cy.createWorkspace('Memory Test').then(ws => {
      workspaceId = ws.workspace_id
    })
  })

  it('can save a memory via API and see it in stats', () => {
    cy.saveMemory(workspaceId, 'TurboQuant achieves 3.8x compression', 'finding', 'Compression Result')

    cy.visit(`/workspace/${workspaceId}`)
    // Create a session to see the workspace layout
    cy.contains('New Session').first().click()

    // Project state panel should show the memory
    cy.contains('Recent Memories')
    cy.contains('Compression Result')
    cy.contains('finding')
  })

  it('memory persists after page reload', () => {
    cy.saveMemory(workspaceId, 'Important finding about agent memory', 'finding', 'Agent Memory')

    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()
    cy.contains('Agent Memory')

    // Reload
    cy.reload()
    cy.contains('New Session').first().click()
    cy.contains('Agent Memory')
  })

  it('shows open questions in project state panel', () => {
    cy.saveMemory(workspaceId, 'Should we use Nomic or OpenAI embeddings?', 'question', 'Embedder choice')

    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()

    cy.contains('Open Questions')
    cy.contains('Should we use Nomic or OpenAI embeddings?')
  })
})
