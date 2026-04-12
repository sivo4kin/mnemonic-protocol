describe('API Contract', () => {
  beforeEach(() => {
    cy.resetDb()
  })

  it('health endpoint returns ok', () => {
    cy.request('GET', '/api/health').then(res => {
      expect(res.status).to.eq(200)
      expect(res.body.status).to.eq('ok')
    })
  })

  it('auth session returns local user', () => {
    cy.request('POST', '/api/v1/auth/session').then(res => {
      expect(res.body.ok).to.be.true
      expect(res.body.data.user_id).to.eq('local-user')
    })
  })

  it('workspace CRUD lifecycle', () => {
    // Create
    cy.request('POST', '/api/v1/workspaces', {
      name: 'CRUD Test', description: 'Testing lifecycle', provider: 'openai', model: 'gpt-4o',
    }).then(res => {
      expect(res.body.ok).to.be.true
      const ws = res.body.data
      expect(ws.name).to.eq('CRUD Test')
      expect(ws.current_provider).to.eq('openai')

      // Read
      cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}`).then(r => {
        expect(r.body.data.name).to.eq('CRUD Test')
      })

      // Update
      cy.request('PATCH', `/api/v1/workspaces/${ws.workspace_id}`, {
        name: 'Updated Name',
      }).then(r => {
        expect(r.body.data.name).to.eq('Updated Name')
      })

      // List
      cy.request('GET', '/api/v1/workspaces').then(r => {
        expect(r.body.data.length).to.be.greaterThan(0)
      })
    })
  })

  it('session and message lifecycle', () => {
    cy.createWorkspace('Msg Test').then(ws => {
      // Create session
      cy.request('POST', `/api/v1/workspaces/${ws.workspace_id}/sessions`, {
        title: 'Test Session',
      }).then(res => {
        const sess = res.body.data
        expect(sess.title).to.eq('Test Session')
        expect(sess.status).to.eq('active')

        // List sessions
        cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/sessions`).then(r => {
          expect(r.body.data.length).to.eq(1)
        })

        // List messages (empty)
        cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/sessions/${sess.session_id}/messages`).then(r => {
          expect(r.body.data.length).to.eq(0)
        })
      })
    })
  })

  it('memory CRUD and search', () => {
    cy.createWorkspace('Mem CRUD').then(ws => {
      // Create
      cy.request('POST', `/api/v1/workspaces/${ws.workspace_id}/memories`, {
        content: 'Scalar quantization preserves recall at 8-bit',
        memory_type: 'finding',
        title: 'Quantization finding',
        tags: ['quantization', 'recall'],
      }).then(res => {
        const mem = res.body.data
        expect(mem.memory_type).to.eq('finding')
        expect(mem.title).to.eq('Quantization finding')
        expect(mem.tags).to.deep.eq(['quantization', 'recall'])

        // Read
        cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/memories/${mem.memory_id}`).then(r => {
          expect(r.body.data.content).to.include('Scalar quantization')
        })

        // Update
        cy.request('PATCH', `/api/v1/workspaces/${ws.workspace_id}/memories/${mem.memory_id}`, {
          title: 'Updated Title',
          is_pinned: true,
        }).then(r => {
          expect(r.body.data.title).to.eq('Updated Title')
          expect(r.body.data.is_pinned).to.be.true
        })
      })

      // Search
      cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/memories?q=quantization`).then(res => {
        expect(res.body.data.length).to.be.greaterThan(0)
        expect(res.body.data[0]).to.have.property('relevance_score')
      })

      // Filter by type
      cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/memories?type=finding`).then(res => {
        expect(res.body.data.length).to.eq(1)
      })
    })
  })

  it('provider binding and switch', () => {
    cy.createWorkspace('Provider Test', 'openai', 'gpt-4o').then(ws => {
      // Get current binding
      cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/provider-binding`).then(res => {
        expect(res.body.data.provider).to.eq('openai')
        expect(res.body.data.model).to.eq('gpt-4o')
      })

      // Switch
      cy.request('POST', `/api/v1/workspaces/${ws.workspace_id}/provider-binding/switch`, {
        provider: 'anthropic', model: 'claude-sonnet-4-20250514',
      }).then(res => {
        expect(res.body.data.provider).to.eq('anthropic')
        expect(res.body.data.message).to.include('preserved')
      })

      // Verify
      cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}`).then(res => {
        expect(res.body.data.current_provider).to.eq('anthropic')
        expect(res.body.data.current_model).to.eq('claude-sonnet-4-20250514')
      })
    })
  })

  it('workspace stats', () => {
    cy.createWorkspace('Stats Test').then(ws => {
      cy.saveMemory(ws.workspace_id, 'Finding 1', 'finding')
      cy.saveMemory(ws.workspace_id, 'Question 1', 'question')
      cy.createSession(ws.workspace_id, 'Sess 1')

      cy.request('GET', `/api/v1/workspaces/${ws.workspace_id}/stats`).then(res => {
        const s = res.body.data
        expect(s.memory_count).to.eq(2)
        expect(s.session_count).to.eq(1)
        expect(s.open_questions.length).to.eq(1)
        expect(s.recent_memories.length).to.eq(2)
      })
    })
  })
})
