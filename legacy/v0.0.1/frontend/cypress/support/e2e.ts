/// <reference types="cypress" />

// Custom commands for common operations

Cypress.Commands.add('createWorkspace', (name: string, provider = 'openai', model = 'gpt-4o') => {
  cy.request('POST', '/api/v1/workspaces', {
    name,
    description: `Test workspace: ${name}`,
    provider,
    model,
  }).then(res => {
    expect(res.status).to.eq(200)
    expect(res.body.ok).to.be.true
    return res.body.data
  })
})

Cypress.Commands.add('createSession', (workspaceId: string, title?: string) => {
  cy.request('POST', `/api/v1/workspaces/${workspaceId}/sessions`, {
    title: title || 'Test Session',
  }).then(res => {
    expect(res.status).to.eq(200)
    return res.body.data
  })
})

Cypress.Commands.add('saveMemory', (workspaceId: string, content: string, memoryType = 'finding', title?: string) => {
  cy.request('POST', `/api/v1/workspaces/${workspaceId}/memories`, {
    content,
    memory_type: memoryType,
    title,
  }).then(res => {
    expect(res.status).to.eq(200)
    return res.body.data
  })
})

Cypress.Commands.add('resetDb', () => {
  // Delete all workspaces via API (clean slate for each test)
  cy.request('GET', '/api/v1/workspaces').then(res => {
    const workspaces = res.body.data || []
    workspaces.forEach((ws: { workspace_id: string }) => {
      cy.request('PATCH', `/api/v1/workspaces/${ws.workspace_id}`, { status: 'deleted' })
    })
  })
})

declare global {
  namespace Cypress {
    interface Chainable {
      createWorkspace(name: string, provider?: string, model?: string): Chainable<any>
      createSession(workspaceId: string, title?: string): Chainable<any>
      saveMemory(workspaceId: string, content: string, memoryType?: string, title?: string): Chainable<any>
      resetDb(): Chainable<void>
    }
  }
}

export {}
