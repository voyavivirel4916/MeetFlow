import {afterEach,expect,it,vi} from 'vitest'
import {resetApi,resetValidation} from '../src/auth/reset'
afterEach(()=>vi.unstubAllGlobals())
it('validates email, new password and confirmation',()=>{
 expect(resetValidation('wrong','','',false)).toBeTruthy()
 expect(resetValidation('student@example.com','','',false)).toBe('')
 expect(resetValidation('','short','short',true)).toBeTruthy()
 expect(resetValidation('','NewPassword123','different',true)).toBeTruthy()
 expect(resetValidation('','NewPassword123','NewPassword123',true)).toBe('')
})
it('sends reset secrets only in request body',async()=>{
 const id='c07e357967c148068a4f9aa539c759e2'
 const fetch=vi.fn().mockImplementation(()=>Promise.resolve(new Response(JSON.stringify({data:{message:'已处理'},request_id:id}),{headers:{'Content-Type':'application/json','X-Request-ID':id}})))
 vi.stubGlobal('fetch',fetch)
 await resetApi.confirm('private-token','private-password')
 expect(fetch).toHaveBeenCalledWith('/api/v1/auth/password-reset/confirm',expect.objectContaining({body:JSON.stringify({token:'private-token',password:'private-password'})}))
 await resetApi.request(' STUDENT@example.com ')
 expect(fetch).toHaveBeenLastCalledWith('/api/v1/auth/password-reset/request',expect.objectContaining({body:JSON.stringify({email:'student@example.com'})}))
})
it('treats unconfigured email as an explicit rejection, not an uncertain send',async()=>{
 const id='c07e357967c148068a4f9aa539c759e2'
 vi.stubGlobal('fetch',vi.fn().mockResolvedValue(new Response(JSON.stringify({error:{code:'MAIL_UNAVAILABLE',message:'暂未开放'},request_id:id}),{status:503,headers:{'Content-Type':'application/json','X-Request-ID':id}})))
 await expect(resetApi.request('student@example.com')).rejects.toMatchObject({code:'MAIL_UNAVAILABLE',uncertain:false})
})
