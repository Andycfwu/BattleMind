// Only used in the project-owned local checkout; never bind this to a LAN address.
exports.port = 8000;
exports.bindaddress = '127.0.0.1';
exports.nothrottle = true;
exports.noguestsecurity = true;
exports.noipchecks = true;
exports.subprocesses = 0;
exports.repl = false;
exports.watchconfig = false;
exports.reportbattles = false;
// The official engine writes committed choices at battle end. Recorder-only data.
exports.logchallenges = true;
exports.logsdir = process.env.BATTLEMIND_LOG_DIR || './logs';
exports.logladderip = false;
exports.loginserver = 'http://127.0.0.1:1/';
exports.routes = {root: '127.0.0.1', client: '127.0.0.1', dex: '127.0.0.1', replays: '127.0.0.1'};
