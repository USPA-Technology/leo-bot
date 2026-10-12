const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { test } = require("node:test");

const source = fs.readFileSync(
  path.join(__dirname, "../resources/js/leocdp.chatbot.js"),
  "utf8"
);

function setupChat() {
  const requests = [];
  const answers = [];
  const errors = [];
  const removedLoaders = [];
  const statusMessages = [];
  const eventSources = [];
  const cache = new Map();
  let promptCount = 0;

  class FakeEventSource {
    constructor(url) {
      this.url = url;
      this.listeners = {};
      this.closed = false;
      eventSources.push(this);
    }

    addEventListener(name, callback) {
      this.listeners[name] = callback;
    }

    close() {
      this.closed = true;
    }
  }

  function jquery() {
    return {
      find() { return this; },
      on() { return this; },
      trigger() { return this; },
      slice() { return this; },
      map() { return this; },
      get() { return ["Previous conversation"]; },
    };
  }
  jquery.ajax = options => {
    const request = { options };
    requests.push(request);
    return {
      done(callback) {
        request.success = callback;
        return this;
      },
    };
  };

  const context = vm.createContext({
    window: { addEventListener() {} },
    document: {},
    console: { log() {}, info() {}, warn() {}, error() {} },
    $: jquery,
    BASE_URL_LEOBOT: "https://leobot.test/_leoai/ask",
    EventSource: FakeEventSource,
    URL,
    CDP_TRACKING: false,
    lscache: { set(key, value) { cache.set(key, value); } },
  });
  vm.runInContext(source, context);
  context.currentUserProfile.visitorId = "visitor";
  context.currentUserProfile.touchpointId = "tp";
  context.currentUserProfile.latitude = 10.747904;
  context.currentUserProfile.longitude = 106.6467328;
  context.showChatBotLoader = () => Promise.resolve(7);
  context.getBotUI = () => ({
    message: {
      remove(index) { removedLoaders.push(index); },
      add(message) { statusMessages.push(message); },
    },
  });
  context.leoBotShowAnswer = answer => answers.push(answer);
  context.leoBotPromptQuestion = () => { promptCount += 1; };
  context.leoBotShowError = (message, nextAction) => {
    errors.push(message);
    nextAction();
  };
  return {
    context, requests, answers, errors, removedLoaders, statusMessages,
    eventSources, cache,
    promptCount: () => promptCount,
  };
}

test("loads the greeting without waiting for optional geolocation", async () => {
  const chat = setupChat();
  let greetedName;
  chat.context.window.currentUserProfile = chat.context.currentUserProfile;
  chat.context.navigator = {
    geolocation: {
      getCurrentPosition() {},
    },
  };
  chat.context.BASE_URL_TOUCHPOINT = "https://leobot.test/touchpoint";
  chat.context.BASE_URL_GET_VISITOR_INFO = "https://leobot.test/visitor-info";
  chat.context.lscache.get = () => null;
  chat.context.$.getJSON = () =>
    Promise.resolve({ error_code: 0, name: "Ada" });
  chat.context.chatbotUI.initialize = () => {};
  chat.context.loadChatSessionWithProfile = () => {};
  chat.context.showLeoChatBot = name => { greetedName = name; };

  chat.context.initLeoChatBot("leobot_website", "visitor");
  await Promise.resolve();
  await Promise.resolve();

  assert.equal(greetedName, "Ada");
});

for (const choice of ["1", "2", "3", "4", "5", " 4 "]) {
  test(`sends single-digit place selection ${JSON.stringify(choice)}`, async () => {
    const chat = setupChat();
    chat.context.sendQuestionToLeoAI("ask", choice);
    await Promise.resolve();

    assert.equal(chat.requests.length, 1);
    const request = chat.requests[0];
    assert.equal(request.options.url, "https://leobot.test/_leoai/ask");
    const payload = JSON.parse(request.options.data);
    assert.equal(payload.question, choice.trim());
    assert.equal(payload.visitor_id, "visitor");
    assert.equal(payload.touchpoint_id, "tp");
    assert.equal(payload.latitude, 10.747904);
    assert.equal(payload.longitude, 106.6467328);
    assert.equal(payload.answer_in_format, "html");

    const confirmation = "<p>Bạn đã chọn <strong>Cha Tam Church</strong>.</p>";
    request.success({ error_code: 0, answer: confirmation, touchpoint_id: "tp" });
    assert.deepEqual(chat.answers, [confirmation]);
    assert.deepEqual(chat.removedLoaders, [7]);
  });
}

test("continues sending normal questions", async () => {
  const chat = setupChat();
  chat.context.sendQuestionToLeoAI("ask", "  Tell me about this church  ");
  await Promise.resolve();
  assert.equal(
    JSON.parse(chat.requests[0].options.data).question,
    "Tell me about this church"
  );
});

test("blank input shows feedback and restores the question prompt", async () => {
  const chat = setupChat();
  chat.context.sendQuestionToLeoAI("ask", "   ");
  await Promise.resolve();
  assert.equal(chat.requests.length, 0);
  assert.equal(chat.errors.length, 1);
  assert.equal(chat.promptCount(), 1);
});

test("exit remains local and is not sent to the API", async () => {
  const chat = setupChat();
  chat.context.sendQuestionToLeoAI("ask", "exit");
  await Promise.resolve();
  assert.equal(chat.requests.length, 0);
});

test("failed selection request clears its loader and restores the prompt", async () => {
  const chat = setupChat();
  chat.context.sendQuestionToLeoAI("ask", "4");
  await Promise.resolve();
  chat.requests[0].options.error({}, "network error");
  assert.deepEqual(chat.removedLoaders, [7]);
  assert.equal(chat.errors.length, 1);
  assert.equal(chat.promptCount(), 1);
});

test("refreshes the latest user question after enrichment succeeds", async () => {
  const chat = setupChat();
  chat.context.window.LEO_UI_LANGUAGE = "en";
  chat.context.sendQuestionToLeoAI("ask", "coffee near me");
  await Promise.resolve();

  chat.requests[0].success({
    error_code: 0,
    answer: "I queued a place search.",
    enrichment_status_url: "/_leoai/geo-places/enrichment/run-id/events",
  });

  assert.equal(chat.eventSources.length, 1);
  const source = chat.eventSources[0];
  assert.equal(
    source.url,
    "https://leobot.test/_leoai/geo-places/enrichment/run-id/events"
  );

  source.onmessage({ data: JSON.stringify({ run_id: "run-id", status: "STARTED" }) });
  assert.match(chat.statusMessages[0].content, /place search is running/i);
  assert.equal(source.closed, false);

  chat.context.sendQuestionToLeoAI("ask", "latest user question");
  await Promise.resolve();
  chat.requests[1].success({ error_code: 0, answer: "latest response" });

  source.onmessage({ data: JSON.stringify({ run_id: "run-id", status: "SUCCESS" }) });
  await Promise.resolve();
  assert.match(chat.statusMessages[1].content, /checking updated results/i);
  assert.equal(source.closed, true);
  assert.equal(chat.requests.length, 3);
  assert.equal(
    JSON.parse(chat.requests[2].options.data).question,
    "latest user question"
  );

  chat.requests[2].success({
    error_code: 0,
    answer: "The refreshed request queued another search.",
    enrichment_status_url: "/_leoai/geo-places/enrichment/second-run/events",
  });
  const secondSource = chat.eventSources[1];
  secondSource.onmessage({
    data: JSON.stringify({ run_id: "second-run", status: "SUCCESS" }),
  });
  assert.equal(secondSource.closed, true);
  assert.equal(chat.requests.length, 3);
});
