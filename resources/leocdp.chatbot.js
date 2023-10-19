const dnsDomainLeoBot = 'leobot.example.com';
const baseLeoBotUrl = location.protocol + '//' + dnsDomainLeoBot;
var currentUserProfile = {"userLogin":"demo", "displayName": "Friend"}		

const BASE_URL_LEOBOT = baseLeoBotUrl + '/ask';
const IS_LEO_BOT_READY = dnsDomainLeoBot !== "";

var leoBotUI = false;
function getBotUI(){
	if(leoBotUI === false){
		leoBotUI = new BotUI('LEO_ChatBot_Container');	
	}
	return leoBotUI;
}

function initLeoChatBot(context) {
	$('#leoChatBotDialog').modal({ backdrop: 'static', keyboard: false});
	getBotUI().message.removeAll();
	showLeoChatBot();
}

var showLeoChatBot = function() {
	
	getBotUI().message.bot('Hi ' + currentUserProfile.displayName + ', how can LEO help you ?')
		.then(function() {
			leoBotAskKeywords();
		});
}

var leoBotAskKeywords = function() {
	getBotUI().message.bot({
		delay: 500,
		content: 'Please enter your question: '
	})
	.then(function() {
		return getBotUI().action.text({
			delay: 1000,
			action: {
				size: 80,
				icon: 'question',
				value: '', // show the prevous answer if any
				placeholder: 'Enter your question'
			}
		})
	}).then(function(res) {
		leoBotRecommendation('ask', res.value);	
	});
}


var leoBotRecommendation = function(context, content) {
	if (content.length > 1 && content !== "exit") {
		var chatLoader = getBotUI().message.add({
			delay: 10000,
			loading: true,
			content: ''
		});
		console.log(chatLoader)

		var callback = function(loader, data) {
			loader.then(function (index) {
				// get the index of the empty message and delete it
				getBotUI().message.remove(index);
			});

			if (typeof data.answer === 'string') {
				var answerInRaw = data.answer.trim();
				var answerInHtml = marked.parse(answerInRaw);

				if ('ask' === context) {
					getBotUI().message.add({ human: false, content: answerInHtml, type: 'html' });
					setTimeout(function() {
						$('div.botui-message').find('a').attr('target', '_blank');
					}, 1000);

					// next question
					leoBotAskKeywords()
				}				
			}
			else if (data.error) {
				alert(data.answer)				
			}
			else {
				alert('LEO BOT is getting a system error !')
			}
		};

		

		var lang = $('#leobot_answer_in_language').val()
		var prompt = content;
		var userLogin = currentUserProfile.userLogin;		
		var payload = { 'prompt': prompt, 'content': content, 'usersession': getUserSession(), 'userlogin': userLogin, 'answer_in_language': lang };
		callPostApi(BASE_URL_LEOBOT, payload, chatLoader, callback);
	}
	
}

var callPostApi = function (urlStr, data, chatLoader, okCallback, errorCallback) {
	$.ajax({
		url: urlStr,
		crossDomain: true,
		data: JSON.stringify(data),
		contentType: 'application/json',
		type: 'POST',
		error: function (jqXHR, exception) {
			notifyErrorMessage('WE GET AN ERROR AT URL:' + urlStr);
			if (typeof errorCallback === 'function') {
				errorCallback();
			}
		}
	}).done(function (json) {
		console.log("callPostApi", urlStr, data, json);
		okCallback(chatLoader, json);
	});
}

var getUserSession = function(){
	// In Redis, need: hset demo userlogin demo
	return "demo";
}