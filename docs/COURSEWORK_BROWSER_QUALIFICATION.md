# Student coursework browser qualification

## Purpose

This browser suite qualifies the student-facing coursework resource journey in the Next.js UI. It complements the FastAPI/PostgreSQL integration tests; it does not replace them or claim to validate a live production deployment.

## Automated browser scenarios

1. Student signs in, selects a workspace and subject, loads existing resources and views source-addressable extracted text.
2. Student downloads an authorised source, appends a new immutable version and uploads another resource.
3. Student sees a failed extraction, retries it and is not offered cohort sharing when the staff policy is disabled.
4. Student opens the camera scanner, captures a page using Chromium's fake camera, assembles a PDF and sees it ready for upload.

The API is deliberately mocked at the HTTP boundary in these browser tests. Real database ownership, role isolation, malware scanning, object storage integrity, queue recovery and OCR are covered by the backend integration/worker test suites.

## Local execution

```bash
npm install
npx playwright install --with-deps chromium
npm run test:e2e
```

The test runner starts the Next.js development server automatically. CI runs the same suite after frontend typecheck, lint and production build checks.

## Qualification limitations

- The camera scenario uses Chromium's fake camera device. It verifies the capture-to-PDF browser workflow, not physical-device camera quality, autofocus, page-edge detection, glare correction or iOS/Android browser compatibility.
- The API is mocked. Run the backend integration suite for real authorization and persistence; run staging qualification for live malware scanning, object storage, worker processing and OCR.
- Accessibility is currently checked through semantic labels, roles and keyboard-operable native controls in the exercised flows. A full WCAG 2.2 AA audit and assistive-technology testing remain release gates.
