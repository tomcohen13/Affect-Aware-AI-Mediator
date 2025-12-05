"""Unit tests for the affective mediator"""
import pytest
import datetime
from agent.affective_mediator import AffectiveMediator
from langchain_core.messages import HumanMessage, SystemMessage
from agent.tests.test_base_models import create_affective_event, create_initial_state

mediator = AffectiveMediator()

react = mediator.react_agent


@pytest.mark.asyncio
async def test_should_intervene():
    config={'configurable': {'thread_id': '1'}}
    messages = [
        HumanMessage(content='User _mmabcq8vb sent: Honestly I think trump should be able to stay a third term; he handled national security very well.'),
        HumanMessage(content='User _nvdfegbfv sent: I agree\n        '),
        HumanMessage(content='User _bcexy2dnq sent: I disagree', additional_kwargs={'participant_id': '_bcexy2dnq'}),
    ]
    result = await react.ainvoke(
        input={
            'messages': messages,
            'topic': 'Third presidential term: FDR did it. Should we do it again?',
            'post_intervention_cooldown': 30
        },
        config=config,
    )
    assert result['structured_response'].should_intervene == False

@pytest.mark.asyncio
async def test_is_interesting():

    discussion_id = "testy-test"
    e_not_interesting = create_affective_event(modality='text', payload={'content': 'I think this topic is great!'})

    mock_state = create_initial_state()
    
    affective_package = {  # ooops too much?
        "discussion_id": discussion_id,
        "event": e_not_interesting,
        "affective_sperm": mock_state,
    }
            
    _ = await mediator.run(affective_package, pathway="is_interesting")

    config = {'configurable': {'thread_id': discussion_id}}
    next_step = mediator.graph.get_state(config=config)
    # not interesting messaeg, shouldn't be a next node
    assert next_step.next == ()
    
    e_interesting = create_affective_event(
        modality='text',
        payload={'content': "having an AI boyfriend is super legit, stop being robophobic!"}
    )
    affective_package = {  # ooops too much?
        "discussion_id": discussion_id,
        "event": e_interesting,
        "affective_sperm": mock_state,
    }
            
    _ = await mediator.run(affective_package, pathway="is_interesting")

    next_step = mediator.graph.get_state(config=config)
    # interesting, should proceed to affective window
    assert next_step.next == ('affective_window',)

    # 
