const targetHost = "oapi.dingtalk.com"
const targetHostV1 = "api.dingtalk.com"
const targetPathname = ""

export async  function onRequest(context) {	
  // context -> https://developers.cloudflare.com/pages/functions/api-reference/#eventcontext
 
  const request = await context.request.clone()

  const url = new URL(request.url)

  if (url.pathname.startsWith('/hellotalk/v1.0/')){
    url.host = targetHostV1
  }else{
    url.host = targetHost
  }

  url.pathname = url.pathname.replace('/hellotalk', '/' + targetPathname)

  const newUrl = url.toString()
  
  const newRequest = new Request(newUrl, request);
  newRequest.headers.set('Host', targetHost);

  const response = await fetch(newRequest);
  
  return response
}