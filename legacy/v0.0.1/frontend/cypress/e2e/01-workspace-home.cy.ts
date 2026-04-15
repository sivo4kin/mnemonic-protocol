describe('Workspace Home', () => {
  beforeEach(() => {
    cy.resetDb()
  })

  it('shows empty state when no workspaces exist', () => {
    cy.visit('/')
    cy.contains('No workspaces yet')
    cy.contains('New Workspace')
  })

  it('can create a workspace from the home page', () => {
    cy.visit('/')
    cy.contains('New Workspace').click()
    cy.get('input[placeholder="Project name"]').type('AI Research Project')
    cy.get('textarea').type('Investigating compression algorithms')
    cy.contains('Create').click()

    // Should redirect to workspace view
    cy.url().should('include', '/workspace/')
    cy.contains('AI Research Project')
  })

  it('shows created workspace in the list after reload', () => {
    // Create via API
    cy.createWorkspace('Persistent Test').then(ws => {
      cy.visit('/')
      cy.contains('Persistent Test')
      cy.contains('openai/gpt-4o')
    })
  })

  it('can open a workspace from the list', () => {
    cy.createWorkspace('Click to Open').then(ws => {
      cy.visit('/')
      cy.contains('Click to Open').click()
      cy.url().should('include', '/workspace/')
      cy.contains('Click to Open')
    })
  })
})
