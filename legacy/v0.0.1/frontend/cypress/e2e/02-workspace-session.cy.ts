describe('Workspace Sessions', () => {
  let workspaceId: string

  beforeEach(() => {
    cy.resetDb()
    cy.createWorkspace('Session Test').then(ws => {
      workspaceId = ws.workspace_id
    })
  })

  it('shows empty state for new workspace', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('Start a session to begin your research')
    cy.contains('New Session')
  })

  it('can create a new session', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()

    // Session should appear in sidebar
    cy.contains('Session')
    // Chat area should be ready
    cy.contains('Send a message to start the conversation')
  })

  it('shows message input after session is created', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()

    cy.get('input[placeholder="Ask something..."]').should('be.visible')
    cy.get('button').contains('Send').should('be.visible')
  })
})
