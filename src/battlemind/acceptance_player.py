"""Opt-in client class; legacy LocalPlayer and all policy interfaces stay unchanged."""
from .acceptance import ClientRecorder
from .runner import LocalPlayer, close_players


class _JournalTap:
    def __init__(self,writer,player):self.writer,self.player=writer,player

    def write(self,row):
        player=self.player
        # The original LocalPlayer made and serialized this decision. The tap is
        # recorder output only and cannot supply anything to policy.act().
        tag=player.acceptance_room
        player.acceptance_recorder.decision(row,tag,player.trackers[tag].role)
        self.writer.write(row)


class AcceptanceLocalPlayer(LocalPlayer):
    def __init__(self,*,acceptance_recorder: ClientRecorder,**kwargs):
        self.acceptance_recorder=acceptance_recorder
        self.acceptance_room=None
        super().__init__(**kwargs)
        self.journal=_JournalTap(self.journal,self)
        original=self.ps_client.send_message

        async def send(message,room='',message_2=None):
            if not message.startswith('/choose '):
                return await original(message,room,message_2)
            if message_2 is not None:raise ValueError('Bundled choice sends are unsupported')
            attempt,wire=self.acceptance_recorder.begin_send(message,room)
            try:
                result=await original(wire,room)
            except BaseException:
                self.acceptance_recorder.send_result(attempt,False)
                raise
            self.acceptance_recorder.send_result(attempt,True)
            return result

        # Instance-only transport interception: no installed poke-env modifications.
        self.ps_client.send_message=send

    async def _handle_battle_message(self,messages):
        header=messages[0];room=header[0].lstrip('>')
        for line in messages[1:]:
            self.acceptance_room=room
            if len(line)>2 and line[1]=='request' and line[2]:
                self.acceptance_recorder.request(room,line[2])
            # Keep the existing ordered hook. A later line is never read before
            # an earlier request's policy decision and attempt have been captured.
            await super()._handle_battle_message([header,line])


async def close_acceptance_players(players: list[AcceptanceLocalPlayer]) -> None:
    """Seal own journals only after the existing stop/cleanup path has returned.

    The later post-match process can read sealed files. This function never joins
    private data. A failed cleanup leaves explicitly incomplete client journals.
    """
    try:
        await close_players(players)
    except BaseException:
        for player in players:player.acceptance_recorder.close(False)
        raise
    for player in players:player.acceptance_recorder.close()
