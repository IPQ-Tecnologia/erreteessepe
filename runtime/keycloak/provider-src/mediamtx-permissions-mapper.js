var permissions = [];
var readRole = realm.getRole("teste-mediamtx");

if (readRole && user.hasRole(readRole)) {
    permissions.push({
        "action": "read",
        "path": ""
    });
}

exports = Java.asJSONCompatible(permissions);
