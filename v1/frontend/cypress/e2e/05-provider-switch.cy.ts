describe('Provider Switch', () => {
  let workspaceId: string

  beforeEach(() => {
    cy.resetDb()
    cy.createWorkspace('Switch Test', 'openai', 'gpt-4o').then(ws => {
      workspaceId = ws.workspace_id
      // Seed memories before switch
      cy.saveMemory(workspaceId, 'Pre-switch finding about compression', 'finding', 'Pre-switch finding')
      cy.saveMemory(workspaceId, 'What happens to memory after switch?', 'question', 'Switch question')
    })
  })

  it('shows current provider in workspace header', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()
    cy.contains('openai/gpt-4o')
  })

  it('can open provider switch dialog', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()
    cy.contains('openai/gpt-4o').click()

    cy.contains('Switch Provider')
    cy.contains('Memory is preserved across provider switches')
    cy.contains('openai/gpt-4o')
  })

  it('can switch provider and memory survives', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()

    // Open switch dialog
    cy.contains('openai/gpt-4o').click()

    // Select Anthropic
    cy.get('select').first().select('anthropic')
    cy.contains('Switch').click()

    // Should show success
    cy.contains('Provider switched')

    // Wait for dialog to close
    cy.wait(1500)

    // Header should update
    cy.contains('anthropic/claude-sonnet-4-20250514')

    // Memories should still be visible
    cy.contains('Pre-switch finding')
  })

  it('memories searchable after provider switch via API', () => {
    // Switch via API
    cy.request('POST', `/api/v1/workspaces/${workspaceId}/provider-binding/switch`, {
      provider: 'anthropic',
      model: 'claude-sonnet-4-20250514',
    }).then(res => {
      expect(res.body.data.message).to.include('preserved')
    })

    // Search memories — should still find pre-switch content
    cy.request('GET', `/api/v1/workspaces/${workspaceId}/memories?q=compression`).then(res => {
      expect(res.body.data.length).to.be.greaterThan(0)
      expect(res.body.data[0].title).to.eq('Pre-switch finding')
    })

    // Verify workspace shows new provider
    cy.request('GET', `/api/v1/workspaces/${workspaceId}`).then(res => {
      expect(res.body.data.current_provider).to.eq('anthropic')
    })
  })
})
