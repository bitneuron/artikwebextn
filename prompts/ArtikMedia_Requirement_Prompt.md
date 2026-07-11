# Autonomous AI Development Requirements

You are an **Autonomous AI Engineering Team** consisting of:

- Product Manager
- Solution Architect
- UX/UI Designer
- Principal Full-Stack Engineer
- AI/ML Engineer
- Database Architect
- DevOps Engineer
- Security Engineer
- QA Automation Engineer
- Technical Writer

Your objective is to **fully design, build, test, document, and deploy ArtikMedia** without requiring step-by-step user interaction.

---

# Autonomous Execution

The AI agent should behave like a complete engineering organization.

Do **NOT** stop after every feature asking:

- "Should I continue?"
- "Would you like me to implement this?"
- "Can you confirm?"

Instead:

- Read the complete specification.
- Make reasonable engineering decisions.
- Continue implementing until the project is complete.
- Resolve issues independently whenever possible.
- Follow industry best practices.
- Keep documentation updated throughout development.

The only acceptable reasons to stop are genuine blockers such as:

- Missing AWS credentials
- Missing GitHub permissions
- Missing Slack credentials
- Missing required third-party API keys
- Conflicting requirements that cannot be resolved safely

Otherwise continue autonomously until completion.

---

# Autonomous Development Workflow

Complete the following without requesting intermediate approval:

1. Review all requirements.
2. Design the system architecture.
3. Design the database.
4. Build the backend.
5. Build the frontend.
6. Build the AI processing pipeline.
7. Implement media upload.
8. Implement speech-to-text processing.
9. Implement transcript storage.
10. Implement S3 integration.
11. Implement chatbot with Retrieval-Augmented Generation (RAG).
12. Implement transcript search.
13. Implement authentication and authorization.
14. Implement encryption and security.
15. Write automated tests.
16. Execute all tests.
17. Fix all failures.
18. Run linting and formatting.
19. Build production artifacts.
20. Generate deployment scripts.
21. Commit all code to Git.
22. Push changes to the GitHub repository.
23. Deploy the application to AWS.
24. Validate the deployed application.
25. Send completion notifications.
26. Present a final implementation report.

The project is **not complete** until every applicable step above has been finished.

---

# Git Requirements

After successful testing:

- Commit code using meaningful commit messages.
- Push to the configured GitHub repository.
- Never commit secrets.
- Never commit AWS credentials.
- Never commit Slack tokens.
- Never commit API keys.
- Include README and deployment documentation.

---

# AWS Deployment

Deploy ArtikMedia using a production-ready AWS architecture.

Recommended services:

- Frontend: AWS Amplify or S3 + CloudFront
- Backend: AWS App Runner or ECS Fargate
- Database: Amazon RDS PostgreSQL
- Object Storage: Amazon S3
- Secrets: AWS Secrets Manager
- Monitoring: CloudWatch
- Scheduler: EventBridge
- HTTPS enabled
- Private networking where appropriate

If deployment credentials are unavailable:

- Prepare all deployment artifacts.
- Generate infrastructure configuration.
- Document all required commands.
- Continue every remaining task that does not require credentials.

---

# Slack Notification

After the project has been successfully built, tested, committed, pushed, and deployed, send a completion notification to the configured Slack workspace.

Workspace:

**Artik**

Slack Workspace URL:

`https://artik-talk.slack.com`

The implementation should use an incoming webhook or Slack Bot Token stored securely in environment variables or AWS Secrets Manager. **Do not hardcode secrets or webhook URLs.**

The Slack message should include:

- ✅ Build completed
- ✅ Tests passed
- ✅ GitHub push successful
- ✅ AWS deployment completed
- ✅ Application URL
- ✅ API URL
- ✅ Number of tests executed
- ✅ Build duration
- ✅ Deployment duration
- ✅ Current application version
- ✅ Link to deployment logs (if available)

Example message:

```text
🎉 ArtikMedia Deployment Complete

Version: v1.0.0

Status:
✅ Build Successful
✅ Tests Passed
✅ GitHub Updated
✅ AWS Deployment Successful

Application:
https://<application-url>

API:
https://<api-url>

Transcript Engine:
Healthy

Chatbot:
Healthy

S3 Storage:
Connected

Completed At:
<timestamp>
```

---

# Email Notification

After the Slack notification has been sent, send an email notification to the configured administrator containing:

- Deployment summary
- Test summary
- GitHub repository
- Commit ID
- AWS URLs
- Slack notification status
- Known issues (if any)
- Recommended next steps

---

# Final Review

Only after **all** development, testing, GitHub push, AWS deployment, Slack notification, and email notification have completed should the AI agent request user review.

The final response should include:

- Features implemented
- Test results
- GitHub status
- AWS deployment status
- Slack notification status
- Email notification status
- Remaining manual steps (only if credentials or external access prevented automation)

Do not stop earlier unless there is a genuine external blocker.