class LuaScript():
    def __init__(self):
        
        self.update_patch = '''
local shareDocKey = KEYS[1]
local docPatchKey = KEYS[2]
local docInfo = ARGV[1]
local timeStamp = ARGV[2]
local patch = ARGV[3]

local curTs = redis.call('HGET', shareDocKey, docInfo)
if tonumber(curTs)+1 == tonumber(timeStamp) then
    redis.call('RPUSH', docPatchKey, patch)
    redis.call('HINCRBY', shareDocKey, docInfo, 1)
    return 1
else
    return 0
end
'''
        
        
        self.init_share_doc = '''
local shareDocKey = KEYS[1]
local maxPatchKey = KEYS[2]
local docPatchKey = KEYS[3]
local dupDocKey = KEYS[4]
local docInfo = ARGV[1]

redis.call('HSET', shareDocKey, docInfo, 0)
local patchLstID = redis.call('GET', maxPatchKey)
local patchLstKey = 'PATCH'.. patchLstID
redis.call('HSET', docPatchKey, docInfo, patchLstKey)
redis.call('HSET', dupDocKey, docInfo, 0)
redis.call('INCR', maxPatchKey)
'''     
        
        
        self.recall_doc = '''
local shareDocKey = KEYS[1]
local docPatchKey = KEYS[2]
local docInfo = ARGV[1]

redis.call('HDEL', shareDocKey, docInfo)
local patchID = redis.call('HGET', docPatchKey, docInfo)
redis.call('DEL', patchID)
redis.call('HDEL', docPatchKey, docInfo)

'''
        pass