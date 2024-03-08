const targetHost = "api.anthropic.com"
const targetPathname = ""

export async  function onRequest(context) {	
  // context -> https://developers.cloudflare.com/pages/functions/api-reference/#eventcontext
 
  const request = await context.request.clone()

  const url = new URL(request.url)
  url.host = targetHost
  url.pathname = url.pathname.replace('/helloclaude', '/' + targetPathname)
  const newUrl = url.toString()
  
  const newRequest = new Request(newUrl, request);
  newRequest.headers.set('Host', targetHost);

  const response = await fetch(newRequest);
  
  return response
}