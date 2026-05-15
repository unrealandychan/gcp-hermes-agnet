'use client'

import { signIn, useSession } from 'next-auth/react'
import { useEffect } from 'react'
import { useRouter } from 'next/navigation'

export default function LoginPage() {
  const { status } = useSession()
  const router = useRouter()

  useEffect(() => {
    if (status === 'authenticated') router.push('/chat')
  }, [status, router])

  return (
    <div className="flex min-h-screen items-center justify-center">
      <div className="rounded-2xl bg-gray-900 p-10 shadow-xl text-center space-y-6 w-80">
        <h1 className="text-2xl font-semibold tracking-tight">Hermes</h1>
        <p className="text-gray-400 text-sm">Enterprise AI Assistant</p>
        <button
          onClick={() => signIn('google')}
          className="w-full rounded-lg bg-blue-600 hover:bg-blue-500 py-3 text-sm font-medium transition-colors"
        >
          Sign in with Google
        </button>
      </div>
    </div>
  )
}
