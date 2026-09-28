// notification_dispatch -- inserts a row into `notifications`, which the
// realtime channel fans out to the user (Developer Spec.md §8.7).
import { createClient } from "https://esm.sh/@supabase/supabase-js@2";

Deno.serve(async (req) => {
  const { user_id, kind, payload } = await req.json();
  if (!user_id || !kind) {
    return new Response(
      JSON.stringify({ error: "user_id and kind are required" }),
      { status: 400, headers: { "Content-Type": "application/json" } },
    );
  }

  const supabase = createClient(
    Deno.env.get("SUPABASE_URL")!,
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY")!,
  );

  const { error } = await supabase
    .from("notifications")
    .insert({ user_id, kind, payload: payload ?? {} });
  if (error) {
    return new Response(JSON.stringify({ error: error.message }), {
      status: 500,
      headers: { "Content-Type": "application/json" },
    });
  }

  return new Response(JSON.stringify({ ok: true }), {
    status: 200,
    headers: { "Content-Type": "application/json" },
  });
});
