import type { NextRequest } from 'next/server'

const DEFAULT_BACKEND_URL = 'http://127.0.0.1:8000'

type RouteContext = { params: Promise<{ path: string[] }> }

function isAllowedRoute(path: string, method: string): boolean {
  if (path === 'api/v1/auth/login') return method === 'POST'
  if (path === 'api/v1/auth/me') return method === 'GET'
  if (path === 'api/v1/patients') return method === 'GET' || method === 'POST'
  if (path === 'api/v1/encounters') return method === 'GET' || method === 'POST'

  if (/^api\/v1\/patients\/[A-Za-z0-9_-]+$/.test(path)) return method === 'GET'
  if (/^api\/v1\/patients\/[A-Za-z0-9_-]+\/workspace$/.test(path)) return method === 'GET'

  if (path === 'api/v1/follow-ups') return method === 'GET' || method === 'POST'
  if (/^api\/v1\/follow-ups\/[A-Za-z0-9_-]+$/.test(path)) return method === 'GET' || method === 'PATCH'

  return false
}


async function proxy(request: NextRequest, context: RouteContext): Promise<Response> {
  const { path: segments } = await context.params
  const path = segments.join('/')
  const method = request.method.toUpperCase()

  // Intentionally restrict the proxy to the read-only patient integration and login.
  if (!isAllowedRoute(path, method)) {
    return Response.json({ detail: 'This frontend proxy route is not enabled.' }, { status: 404 })
  }

  const backendBaseUrl = (process.env.BACKEND_API_URL || DEFAULT_BACKEND_URL).replace(/\/+$/, '')
  const incomingUrl = new URL(request.url)
  const targetUrl = `${backendBaseUrl}/${path}${incomingUrl.search}`
  const headers = new Headers({ Accept: 'application/json' })
  const authorization = request.headers.get('authorization')
  const contentType = request.headers.get('content-type')
  if (authorization) headers.set('Authorization', authorization)
  if (contentType) headers.set('Content-Type', contentType)

  try {
    const upstream = await fetch(targetUrl, {
      method,
      headers,
      body: method === 'GET' || method === 'HEAD' ? undefined : await request.text(),
      cache: 'no-store',
    })
    const responseBody = await upstream.text()
    return new Response(responseBody, {
      status: upstream.status,
      headers: {
        'Content-Type': upstream.headers.get('content-type') || 'application/json',
        'Cache-Control': 'no-store',
      },
    })
  } catch {
    return Response.json(
      { detail: 'FastAPI backend is unreachable. Start it at the configured BACKEND_API_URL.' },
      { status: 502 },
    )
  }
}

export async function GET(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context)
}

export async function POST(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context)
}
export async function PATCH(request: NextRequest, context: RouteContext): Promise<Response> {
  return proxy(request, context)
}