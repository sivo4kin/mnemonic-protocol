import { defineConfig } from 'cypress'

export default defineConfig({
  e2e: {
    baseUrl: 'http://127.0.0.1:8000',
    supportFile: 'cypress/support/e2e.ts',
    video: false,
    screenshotOnRunFailure: false,
    defaultCommandTimeout: 10000,
  },
})
