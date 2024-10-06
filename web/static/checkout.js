'use strict';

// This is your test secret API key.
var stripe = Stripe("pk_test_G9In1RiFRV4LCwfDGOxiX6he");

const query = window.location.search;
const params = new URLSearchParams(query);
const isbn = params.get('isbn');

// Create a Checkout Session
async function initialize() {
  const fetchClientSecret = async () => {
    let formData = new FormData();
    formData.append('isbn',isbn)
    const response = await fetch("/create-checkout-session", {
      body: formData,
      method: "POST",
    });
    const { clientSecret } = await response.json();
    return clientSecret;
  };

    // console.log(fetchClientSecret);
  const checkout = await stripe.initEmbeddedCheckout({
    fetchClientSecret,
  });

  // Mount Checkout
  checkout.mount('#checkout');
}

initialize();

