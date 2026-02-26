import { streamText } from 'ai'
import { createAnthropic } from '@ai-sdk/anthropic'

export async function POST(req: Request) {
  const { emailSubject, emailSender, emailBody } = await req.json()

  if (!emailSubject || !emailSender || !emailBody) {
    return new Response('Missing required fields', { status: 400 })
  }

  const apiKey = process.env.ANTHROPIC_API_KEY
  if (!apiKey) {
    return new Response('ANTHROPIC_API_KEY environment variable not set', { status: 500 })
  }

  const anthropic = createAnthropic({ apiKey })

  const systemPrompt = `You are a professional email assistant. Write a concise, courteous reply to the email below. 
Write in first person as the email recipient. Keep the reply to 2-3 sentences maximum unless more detail is needed.
Be professional but friendly. Do not include greetings like "Hi [Name]" - the user will add those. 
Just write the body of the reply.`

  const userMessage = `Original email from ${emailSender}:
Subject: ${emailSubject}

${emailBody}`

  const result = streamText({
    model: anthropic('claude-haiku-4-5-20251001'),
    system: systemPrompt,
    messages: [
      {
        role: 'user',
        content: userMessage,
      },
    ],
  })

  return result.toTextStreamResponse()
}
