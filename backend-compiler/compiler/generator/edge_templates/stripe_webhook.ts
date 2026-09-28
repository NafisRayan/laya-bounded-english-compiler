// stripe_webhook -- records Stripe payment events (Developer Spec.md §8.7).
// Set STRIPE_WEBHOOK_SECRET among the project's function secrets.
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async (req) => {
  if (!req.headers.get("stripe-signature")) {
    return new Response(JSON.stringify({ error: "missing stripe-signature" }), {
      status: 400,
      headers: { "Content-Type": "application/json" },
    });
  }

  const event = await req.json();
  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  if (event.type === "payment_intent.succeeded") {
    const { error } = await supabase
      .from("payments")
      .update({ status: "succeeded" })
      .eq("provider_ref", event.data.object.id);
    if (error) {
      return new Response(JSON.stringify({ error: error.message }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      });
    }
  }

  return new Response(JSON.stringify({ received: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
