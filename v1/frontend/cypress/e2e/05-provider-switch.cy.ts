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

  it('session and message history survives provider switch', () => {
    // 1. Create a session with openai
    cy.request('POST', `/api/v1/workspaces/${workspaceId}/sessions`, {
      title: 'Continuity session',
    }).then(sessRes => {
      const sessionId = sessRes.body.data.session_id

      // 2. Send a message BEFORE switch (this calls openai provider)
      //    Will fail to call the actual LLM (no API key), but the user
      //    message and error response are still persisted
      cy.request('POST', `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/messages`, {
        content: 'What is TurboQuant compression ratio?',
        top_k_memories: 5,
      }).then(askRes => {
        // User message should be saved regardless of provider success
        expect(askRes.body.ok).to.be.true
        const preMessages = [
          askRes.body.data.user_message,
          askRes.body.data.assistant_message,
        ]
        expect(preMessages[0].role).to.eq('user')
        expect(preMessages[0].content).to.eq('What is TurboQuant compression ratio?')
        expect(preMessages[1].role).to.eq('assistant')

        // 3. Verify messages exist pre-switch
        cy.request('GET', `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/messages`).then(res => {
          expect(res.body.data.length).to.eq(2)
          expect(res.body.data[0].content).to.eq('What is TurboQuant compression ratio?')
        })

        // 4. Switch provider: openai → anthropic
        cy.request('POST', `/api/v1/workspaces/${workspaceId}/provider-binding/switch`, {
          provider: 'anthropic',
          model: 'claude-sonnet-4-20250514',
        }).then(switchRes => {
          expect(switchRes.body.data.message).to.include('preserved')
        })

        // 5. Verify old messages still exist in the SAME session
        cy.request('GET', `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/messages`).then(res => {
          expect(res.body.data.length).to.eq(2)
          expect(res.body.data[0].role).to.eq('user')
          expect(res.body.data[0].content).to.eq('What is TurboQuant compression ratio?')
        })

        // 6. Send a NEW message to the SAME session with the NEW provider
        cy.request('POST', `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/messages`, {
          content: 'Follow-up: how does this compare to scalar quantization?',
          top_k_memories: 5,
        }).then(postSwitchRes => {
          expect(postSwitchRes.body.ok).to.be.true
          const postMsg = postSwitchRes.body.data.user_message
          expect(postMsg.content).to.eq('Follow-up: how does this compare to scalar quantization?')

          // The assistant response should record the NEW provider
          const asstMsg = postSwitchRes.body.data.assistant_message
          expect(asstMsg.provider_used).to.eq('anthropic')
          expect(asstMsg.model_used).to.eq('claude-sonnet-4-20250514')
        })

        // 7. Verify full conversation history: 4 messages (2 pre + 2 post switch)
        cy.request('GET', `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}/messages`).then(res => {
          expect(res.body.data.length).to.eq(4)
          // First pair was with openai (or error), second pair with anthropic
          expect(res.body.data[0].role).to.eq('user')
          expect(res.body.data[2].role).to.eq('user')
          expect(res.body.data[3].role).to.eq('assistant')
          expect(res.body.data[3].provider_used).to.eq('anthropic')
        })

        // 8. Verify session is still active and usable
        cy.request('GET', `/api/v1/workspaces/${workspaceId}/sessions/${sessionId}`).then(res => {
          expect(res.body.data.status).to.eq('active')
          expect(res.body.data.title).to.eq('Continuity session')
        })
      })
    })
  })
})
