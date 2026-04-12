describe('Source Context', () => {
  let workspaceId: string

  beforeEach(() => {
    cy.resetDb()
    cy.createWorkspace('Source Test').then(ws => {
      workspaceId = ws.workspace_id
    })
  })

  it('can add a pasted note via the workspace panel', () => {
    cy.visit(`/workspace/${workspaceId}`)
    cy.contains('New Session').first().click()

    // Open note input
    cy.contains('+ Add').click()
    cy.get('textarea[placeholder="Paste a note..."]').type('Key reference: TurboQuant paper arXiv:2504.19874')
    cy.contains('Save Note').click()

    // Note should be saved (source count in stats)
    cy.request('GET', `/api/v1/workspaces/${workspaceId}/stats`).then(res => {
      expect(res.body.data.source_count).to.eq(1)
    })
  })

  it('can add a note via API and list it', () => {
    cy.request('POST', `/api/v1/workspaces/${workspaceId}/sources/note`, {
      content: 'Important research note about memory systems',
      display_name: 'Research Note',
    }).then(res => {
      expect(res.body.ok).to.be.true
      expect(res.body.data.source_type).to.eq('pasted_note')
      expect(res.body.data.display_name).to.eq('Research Note')
    })

    cy.request('GET', `/api/v1/workspaces/${workspaceId}/sources`).then(res => {
      expect(res.body.data.length).to.eq(1)
      expect(res.body.data[0].content).to.include('memory systems')
    })
  })
})
